"""engine/entry_radar/four_hour.py — the 4H session grid and C3 (W3, §18 A5.4).

BOUNDARY (contract §2), stated before anything else
---------------------------------------------------
``engine/washout_turn.py`` (WEEKLY washout-turn watch) and ``engine/mtf_upturn.py``
(TS-R3 multi-timeframe upturn, K-of-N legs) are ADJACENT display organs at a
different grain inside a different product.  C3 is a **confirmed-bar** 1D-washout
→ completed-4H-momentum-turn detector producing episodes and events.  Name
similarity is not identity; neither organ is imported or modified here (house
precedent ``engine/washout_turn.py:1-5``).

WHAT C3 IS, AND WHAT IT IS NOT (§18 A5.4)
------------------------------------------
C3 is NOT "C1 fired live, now wait for 4H".  It is a CONFIRMED-BAR detector: its
daily leg is the latest **1D CONFIRMED** canonical StochRSI ``K < 20``, usable
only once that close is knowable — the next session's open, conservatively.  "The
historical parquet already has today's close" is not knowability, and a morning
C3 arm created retroactively from an evening bake is the exact leak §5 exists to
prevent.

THE 4H GRID IS A SESSION OBJECT, NOT A CLOCK OBJECT
----------------------------------------------------
Buckets are anchored at the 09:30 ET session open with a NOMINAL width of 240
minutes, and a bucket's EFFECTIVE END is ``min(start + 240m, the actual exchange
close)``.  A normal session therefore yields a full 09:30–13:30 bucket and a
CLIPPED 13:30–16:00 session-final bucket whose shorter duration is disclosed, and
a 13:00 early close yields ONE bucket ending at 13:00 — never a fabricated 16:00
and never a minute after the bell.  Windows come from
``engine.session_digest.session_window_et``, which is DST-safe and early-close
aware; wall-clock arithmetic is never used (§7).

A bucket is CONFIRMED only at its effective end.  The current incomplete bucket
may be exposed as a ``provisional`` diagnostic and C3@1 may not fire from it: a
live/partial-4H form is a separate detector version, default off (§4).

WARM-UP IS THE INDICATOR'S OWN
-------------------------------
No hand-tuned bar-count floor exists in this module.  C3 is ``unavailable`` until
canonical ``rsi_macd`` has produced enough finite histogram values to evaluate its
three-point predicate.  A hand floor is a second, wrong copy of a mathematical
fact — and it is exactly the kind of constant that drifts from the indicator it
was supposed to describe.

NETWORK STAYS OUT OF THE ENGINE
--------------------------------
Intraday aggregates arrive as an ALREADY-LOADED frame through an injectable
reader seam (:class:`IntradayReader`).  This module opens no socket, reads no
store, and holds no credentials; the bounded per-name REST fetch that feeds it
belongs to a script, and the delayed hourly chart store named in §7.2 is not a C3
substrate at any grain.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Protocol, Sequence

import pandas as pd

from engine.entry_radar import indicator_core as ic
from engine.entry_radar.challengers import (
    BASIS_ADJUSTED,
    ChallengerError,
    DailyHistory,
    DetectorEpisode,
    MinuteBar,
    SessionTape,
    lifecycle,
    rth_minutes,
    utc_iso,
)
from engine.entry_radar.entry_events import (
    RADAR_4H_RECOVERY_SUBTYPE,
    EntryEvent,
    build_radar_native_event,
    sha16,
)
from engine.entry_radar.readings import DetectorReading
from engine.session_digest import session_window_et

C3_DETECTOR_ID = "C3_1D_4H_RECOVERY@1"
C3_VERSION = 1
C3_GRAIN = "1D_confirmed_x_4H_confirmed"
C3_BAR_FAMILY = "rth_session_anchored_4h_grid"

#: Nominal 4H bucket width, in minutes.  NOMINAL — the effective end is clipped to
#: the actual exchange close, which is why a normal session's second bucket is 150
#: minutes long and an early close's only bucket is 210.
FOUR_HOUR_MINUTES = 240

#: C3's turn primitive needs three consecutive finite histogram points.
TURN_POINTS = 3


class C3Error(ChallengerError):
    """A malformed C3 input or an illegal C3 operation."""


C3_SPEC: dict[str, Any] = {
    "detector_id": C3_DETECTOR_ID,
    "version": C3_VERSION,
    "grain": C3_GRAIN,
    "bar_family": C3_BAR_FAMILY,
    "authority_source": "contract §18 A5.4 (2026-08-14 pre-outcome lock)",
    "daily_condition": "latest 1D CONFIRMED canonical StochRSI K < 20",
    "oversold_threshold": ic.OVERSOLD,
    "daily_knowability": ("a confirmed daily close is usable only from the NEXT session "
                          "open (conservative); no same-session final close may create a "
                          "morning arm retrospectively — a historical parquet holding it "
                          "is not knowability (§5)"),
    "arm_rule": "C3 arms when a confirmed 1D washout becomes knowable",
    "turn_rule": ("a NEW completed-4H RSI-MACD histogram turn strictly AFTER the arm; a "
                  "pre-arm 4H turn is stale context and cannot promote"),
    "turn_primitive": "H4_T > H4_prev AND H4_prev <= H4_prev2",
    "grid_anchor": "the 09:30 ET session open",
    "grid_nominal_minutes": FOUR_HOUR_MINUTES,
    "grid_key": "session_open + floor(minutes_since_open / 240) * 240m",
    "grid_effective_end": "min(bucket_start + 240m, the ACTUAL exchange session close)",
    "grid_normal_session": ("09:30-13:30 full bucket + 13:30-16:00 clipped session-final "
                            "bucket, provisional until 16:00 then confirmed with its "
                            "shorter duration disclosed"),
    "grid_early_close": ("the 09:30 bucket clips to the actual close; no fabricated 16:00 "
                         "and no post-close minute"),
    "grid_windows": ("engine.session_digest.session_window_et — DST-safe and early-close "
                     "aware; never wall-clock arithmetic (§7)"),
    "extended_hours": "excluded — RTH only",
    "bucket_confirmation": "a bucket is confirmed only at its effective end",
    "partial_bucket": ("exposed as a provisional diagnostic only; C3@1 may not fire from "
                       "it — a live/partial-4H form is a separate detector version, "
                       "default off (§4)"),
    "indicator": ("canonical RSI-MACD histogram (14/60/5 on RSI, never price MACD, no "
                  "StochRSI second trigger) over the sequence of COMPLETED 4H closes"),
    "warm_up": ("no hand-tuned bar-count floor — unavailable until canonical rsi_macd "
                "produces enough finite histogram values for the 3-point predicate"),
    "turn_points": TURN_POINTS,
    "source_law": ("a bounded per-name intraday aggregate reader behind an injectable "
                   "adapter (adjusted=true, ascending, bounded windows); the delayed "
                   "hourly chart store of §7.2 is never a substrate; no bulk US minute "
                   "crawl and no permanent minute store in W3"),
    "indicator_core": ic.INDICATOR_CORE,
}


def c3_spec_hash() -> str:
    """Stable 16-hex identity of C3's frozen spec block."""
    return sha16(C3_SPEC)


# ---------------------------------------------------------------------------
# the 4H grid
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class FourHourBucket:
    """One 4H-grid bucket, with its clipping and confirmation disclosed.

    ``nominal_minutes`` vs ``effective_minutes`` is the disclosure §18 A5.4 asks
    for: a session-final bucket that ran 150 minutes is not a 240-minute bar, and
    a consumer comparing bar values across sessions has to be able to see that.
    """

    session: str
    index: int
    start: datetime
    effective_end: datetime
    confirmed: bool
    close: float | None
    minutes: int
    nominal_minutes: int = FOUR_HOUR_MINUTES

    @property
    def effective_minutes(self) -> int:
        return int((self.effective_end - self.start).total_seconds() // 60)

    @property
    def clipped(self) -> bool:
        """True when the exchange close cut the bucket short of its nominal width."""
        return self.effective_minutes < self.nominal_minutes

    def to_dict(self) -> dict[str, Any]:
        return {
            "session": self.session,
            "index": self.index,
            "start": utc_iso(self.start),
            "effective_end": utc_iso(self.effective_end),
            "confirmed": self.confirmed,
            "close": self.close,
            "minutes": self.minutes,
            "nominal_minutes": self.nominal_minutes,
            "effective_minutes": self.effective_minutes,
            "clipped": self.clipped,
        }


def four_hour_buckets(tape: SessionTape, *, now: datetime | None = None,
                      nominal_minutes: int = FOUR_HOUR_MINUTES,
                      ) -> tuple[FourHourBucket, ...]:
    """The session's 4H-grid buckets, in order.

    ``now`` is the observation instant.  A bucket is CONFIRMED iff its effective
    end has passed (``effective_end <= now``); with ``now=None`` the session is
    treated as fully elapsed, which is the replay case.  Nothing about the value
    changes on confirmation — only whether C3 may read it.
    """
    open_dt, close_dt = session_window_et(tape.session)
    minutes = rth_minutes(tape)
    width = timedelta(minutes=int(nominal_minutes))
    if width <= timedelta(0):
        raise C3Error("nominal_minutes must be positive")
    out: list[FourHourBucket] = []
    cursor = open_dt
    index = 0
    while cursor < close_dt:
        effective_end = min(cursor + width, close_dt)
        inside = [m for m in minutes
                  if m.start >= cursor and m.knowable_at <= effective_end]
        out.append(FourHourBucket(
            session=tape.session.isoformat(), index=index, start=cursor,
            effective_end=effective_end,
            confirmed=(now is None or effective_end <= now),
            close=(float(inside[-1].close) if inside else None),
            minutes=len(inside), nominal_minutes=int(nominal_minutes)))
        cursor = effective_end
        index += 1
    return tuple(out)


def confirmed_four_hour_series(buckets: Sequence[FourHourBucket]) -> pd.Series:
    """Closes of the CONFIRMED buckets, indexed by effective end.

    Completed and incomplete 4H bars never mix inside one detector (§4), so the
    filter happens here — once — rather than at each call site where forgetting it
    would be invisible.
    """
    rows = [(b.effective_end, b.close) for b in buckets
            if b.confirmed and b.close is not None]
    if not rows:
        return pd.Series(dtype=float)
    return pd.Series([r[1] for r in rows],
                     index=pd.DatetimeIndex([r[0] for r in rows]))


def four_hour_turn(series: pd.Series) -> bool | None:
    """``H4_T > H4_prev AND H4_prev <= H4_prev2`` — or None inside the warm-up.

    None, never False: while ``rsi_macd`` has fewer than three finite histogram
    points the predicate has not been evaluated, and recording that as "did not
    turn" would count a warm-up as a measured non-fire.
    """
    hist = ic.rsi_macd_hist(series)
    tail = ic.finite_tail(hist, TURN_POINTS)
    if tail is None:
        return None
    prev2, prev, now = tail
    return bool(now > prev and prev <= prev2)


def first_lawful_turn_index(series: pd.Series) -> int | None:
    """The first position at which :func:`four_hour_turn` is evaluable.

    Derived from the indicator, never asserted.  ``tests/`` uses it to pin the
    warm-up MECHANICALLY, so nobody has to maintain a hand-written bar count that
    the indicator can silently outgrow.
    """
    hist = ic.rsi_macd_hist(series)
    finite = pd.Series(hist).notna().to_numpy()
    run = 0
    for position, ok in enumerate(finite):
        run = run + 1 if ok else 0
        if run >= TURN_POINTS:
            return position
    return None


# ---------------------------------------------------------------------------
# the intraday reader seam — network stays outside the engine
# ---------------------------------------------------------------------------

class IntradayReader(Protocol):
    """Return one session's already-loaded minute aggregates.

    A PROTOCOL, so the engine states what it needs without owning how it arrives.
    Production supplies a bounded per-name aggregate fetch (``adjusted=true``,
    ascending, bounded windows); tests supply committed fixtures.  Either way the
    engine performs no IO, which is what keeps CI network-free and what keeps a
    "just this once" fetch out of the math.
    """

    def __call__(self, ticker: str, session: date) -> SessionTape: ...


def tape_from_rows(session: date, rows: Sequence[Sequence[Any]], *,
                   price_basis: str = BASIS_ADJUSTED, vintage: str = "",
                   tz: Any = None) -> SessionTape:
    """Build a :class:`SessionTape` from ``[iso_start, o, h, l, c, v]`` rows.

    The compact array shape is what the committed fixtures carry; keeping the
    parser beside the reader seam means a fixture and a vendor response land in
    exactly the same object.
    """
    bars: list[MinuteBar] = []
    for row in rows:
        start = row[0]
        when = (start if isinstance(start, datetime)
                else datetime.fromisoformat(str(start)))
        if when.tzinfo is None:
            if tz is None:
                raise C3Error(f"minute row {start!r} is naive and no tz was supplied")
            when = when.replace(tzinfo=tz)
        bars.append(MinuteBar(start=when, open=float(row[1]), high=float(row[2]),
                              low=float(row[3]), close=float(row[4]),
                              volume=float(row[5]) if len(row) > 5 else 0.0))
    return SessionTape(session=session, minutes=tuple(bars),
                       price_basis=price_basis, vintage=vintage)


# ---------------------------------------------------------------------------
# C3
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class C3DailyLeg:
    """The confirmed-daily half of C3, with the knowability that governs it."""

    availability: str
    k: float | None
    washed: bool | None
    source_bar_time: str | None
    source_bar_known_at: str | None
    confirmed_bars: int


def c3_daily_leg(daily: DailyHistory, at_session: date) -> C3DailyLeg:
    """Latest 1D CONFIRMED StochRSI K, as knowable at ``at_session``'s open.

    The frame is cut STRICTLY before ``at_session``, so the close that would
    create a same-session arm is not merely ignored — it is never read.  Its
    ``known_at`` is the arming session's own date: that is the "next session open"
    of §5, stated conservatively.
    """
    confirmed = daily.confirmed_through(at_session)
    closes = confirmed["close"].astype(float)
    if len(closes) == 0:
        return C3DailyLeg(availability="unavailable", k=None, washed=None,
                          source_bar_time=None, source_bar_known_at=None,
                          confirmed_bars=0)
    k_series, _d = ic.stoch_rsi_kd(closes)
    k_value = ic.last_finite(k_series)
    source_bar = pd.DatetimeIndex(confirmed.index)[-1].date().isoformat()
    if k_value is None:
        return C3DailyLeg(availability="unavailable", k=None, washed=None,
                          source_bar_time=source_bar,
                          source_bar_known_at=at_session.isoformat(),
                          confirmed_bars=int(len(closes)))
    return C3DailyLeg(availability="confirmed", k=k_value,
                      washed=bool(k_value < ic.OVERSOLD),
                      source_bar_time=source_bar,
                      source_bar_known_at=at_session.isoformat(),
                      confirmed_bars=int(len(closes)))


@dataclass(frozen=True, slots=True)
class C3Run:
    """Readings, the episode and any event from one C3 pass."""

    readings: tuple[DetectorReading, ...]
    episodes: tuple[DetectorEpisode, ...]
    events: tuple[EntryEvent, ...]
    armed_at: str | None = None
    turns: tuple[str, ...] = ()
    provisional: tuple[dict[str, Any], ...] = ()

    @property
    def episode(self) -> DetectorEpisode | None:
        return self.episodes[0] if self.episodes else None


def run_c3(*, ticker: str, daily: DailyHistory,
           buckets_by_session: Sequence[tuple[date, Sequence[FourHourBucket]]],
           ) -> C3Run:
    """Evaluate C3 across a run of sessions.

    ORDER IS THE MECHANISM.  For each session: (1) read the confirmed-daily leg as
    knowable at that session's open and arm if it is washed; (2) walk that
    session's CONFIRMED 4H buckets, appending each to the running completed-4H
    series and testing the turn.  A turn observed before the arm is stale context
    and cannot promote — which is why the arm is evaluated first, and why the
    turn's own history is carried across sessions rather than restarted.
    """
    readings: list[DetectorReading] = []
    events: list[EntryEvent] = []
    episodes: list[DetectorEpisode] = []
    provisional: list[dict[str, Any]] = []
    turns: list[str] = []
    completed: list[FourHourBucket] = []
    live: DetectorEpisode | None = None
    armed_at: str | None = None
    lc = lifecycle()

    for session, buckets in sorted(buckets_by_session, key=lambda row: row[0]):
        leg = c3_daily_leg(daily, session)
        if leg.washed is True and live is None:
            live = DetectorEpisode(ticker=ticker, detector_id=C3_DETECTOR_ID)
            armed_at = session.isoformat()
            live.first_armed_at = armed_at
            live.transition(lc.DetectorState.ARMED, at=armed_at,
                            reason="latest 1D CONFIRMED StochRSI K < 20, knowable at "
                                   "this session's open (A5.4)")
            # Recorded at ARM, not at promotion: an episode that arms and never
            # promotes is a fact the caller must be able to see (§13 — a
            # candidate that never came is not the same as no episode at all).
            episodes.append(live)
        for bucket in buckets:
            if not bucket.confirmed:
                provisional.append(bucket.to_dict())
                continue
            if bucket.close is None:
                continue
            completed.append(bucket)
            series = confirmed_four_hour_series(completed)
            turned = four_hour_turn(series)
            observed_at = utc_iso(bucket.effective_end)
            eligible = armed_at is not None and bucket.session >= armed_at
            availability = ("unavailable" if (turned is None or leg.availability
                                              != "confirmed") else "confirmed")
            condition = None if availability == "unavailable" else bool(
                turned and eligible)
            readings.append(DetectorReading(
                ticker=ticker, detector_id=C3_DETECTOR_ID,
                detector_version=C3_VERSION, detector_spec_hash=c3_spec_hash(),
                variant=None, observed_at=observed_at,
                market_session=bucket.session, availability=availability,
                source_bar_time=utc_iso(bucket.start),
                source_bar_known_at=observed_at, bar_state="confirmed",
                data_vintage=daily.vintage or None,
                features={
                    "daily_k": leg.k,
                    "daily_washed": leg.washed,
                    "daily_source_bar_time": leg.source_bar_time,
                    "daily_source_bar_known_at": leg.source_bar_known_at,
                    "h4_turn": turned,
                    "armed_at": armed_at,
                    "pre_arm": (armed_at is None or bucket.session < armed_at),
                    "completed_4h_bars": len(completed),
                    "bucket_effective_minutes": bucket.effective_minutes,
                    "bucket_clipped": bucket.clipped,
                },
                condition_met=condition,
                evidence_refs=tuple(live.event_ids) if live else ()))
            if turned:
                turns.append(observed_at)
            if condition is True and live is not None and live.candidate_at is None:
                event = build_radar_native_event(
                    detector_id=C3_DETECTOR_ID,
                    detector_spec_hash=c3_spec_hash(),
                    ticker=ticker,
                    family="radar_1d_4h_recovery",
                    subtype=RADAR_4H_RECOVERY_SUBTYPE,
                    signal_ts=observed_at,
                    market_session=bucket.session,
                    bar_state="confirmed",
                    signal_known_ts=observed_at,
                    finality_basis=("confirmed_4h_bucket(effective_end reached; "
                                    "clipped=%s)" % bucket.clipped),
                    context={"h4_close": bucket.close,
                             "bucket_index": bucket.index,
                             "bucket_effective_minutes": bucket.effective_minutes,
                             "daily_k": leg.k,
                             "armed_at": armed_at,
                             "market_session": bucket.session})
                events.append(event)
                live.event_ids.append(str(event.event_id))
                live.candidate_at = observed_at
                live.transition(lc.DetectorState.CANDIDATE, at=observed_at,
                                reason="first post-arm completed-4H histogram turn "
                                       "(A5.4)",
                                evidence_refs=(str(event.event_id),))
    return C3Run(readings=tuple(readings), episodes=tuple(episodes),
                 events=tuple(events), armed_at=armed_at, turns=tuple(turns),
                 provisional=tuple(provisional))
