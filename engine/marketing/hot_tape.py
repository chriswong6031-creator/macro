"""engine.marketing.hot_tape — Hot Tape detectors, FactPacket, intraday state.

Implements research/MARKETING_HOT_TAPE_MASTERPLAN.md §3.2 (attention radar,
v1 detectors) and §3.3 (FactPacket: typed, all numbers engine-computed).

The radar loop is: live quotes + the nightly context pack (hot_tape_pack.py)
-> :func:`detect_events` -> :func:`engine.marketing.hot_tape_wire.compose_wire`
-> outbox item. This module owns the middle step and nothing else: it is PURE
(no I/O in the detectors), deterministic, and makes zero LLM calls. Masterplan
gate 0.3 — "the copy layer may phrase, never originate" — starts here: every
number a post may use is a leaf of ``FactPacket.facts``.

Import discipline (gate 0.6): module-level imports are STDLIB ONLY. yaml is
imported lazily in :func:`load_config`, the jsonl helpers lazily in the ring /
fired accessors, and pandas is never imported at all. The radar workflow runs
on a shallow ubuntu checkout with pyyaml+requests only.

Bridge honesty (masterplan §1, "this stale data issue is so serious"): the
daily price store can lag the live tape. :func:`bridge_ok` reports whether the
pack's trade_date is adjacent to today's session; when it is False every
history-dependent fact (streaks, records, ATH distance, correction/bear
thresholds, RSI) is SUPPRESSED rather than quietly computed against a stale
anchor. The bridge is GLOBAL, so a second, per-record gate rides with it: a
record whose own ``last_date`` lags the pack's tip gets no history facts either
(26 live-quoted laggards sat in the shipped pack, one carrying a "5-day streak"
that had ended six sessions earlier).

Round-number crosses need no history and survive both gates. MCAP MILESTONES
DO NOT: their share count is only trustworthy when the reference's ``asof`` and
the price store's tip are the same date, so ``shares_est`` is None otherwise
and the milestone branch simply never fires (a 2026-07-27 market cap divided by
a 2026-07-02 close inflated JPM's shares 6.5% and manufactured a "$1 trillion"
cross at an actual $942B).

Public API:
    FactPacket                         — the typed fact contract
    load_config(root) / load_pack(root)
    in_window(now, cfg) / session_phase(now) / quotes_fresh(live, now, cfg)
    bridge_ok(pack, now)
    load_ring / append_ring / compact_ring / cross_memory_row
    load_fired / append_fired
    detect_events(...) -> list[FactPacket]
    brief_key(alert_key) / build_brief_packet(alert_row, ...) -> FactPacket | None
    severity_account(packet, cfg) -> str
    packet_to_source(packet, media) -> dict

Never-raise contract: every public function returns None / [] / {} plus one log
line on internal error. Nothing here raises at a seam.
"""
from __future__ import annotations

import copy
import json
import logging
import statistics
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# The session clock is US-Eastern, never UTC (reviewer M6). A window pinned in
# UTC is correct for one half of the year and an hour wrong for the other: the
# shipped 13:25-20:05Z window is 09:25-16:05 ET in EDT but 08:25-15:05 ET in
# EST, so from November the radar would wake an hour before the open and go
# dark for the last hour of every session — the hour that carries the closing
# print. zoneinfo is stdlib (gate 0.6 holds); the import is guarded exactly the
# way live_verify guards its own, so a host with no tzdata degrades instead of
# raising at import time.
try:
    from zoneinfo import ZoneInfo  # noqa: PLC0415

    _ET = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover - tzdata missing
    _ET = None

#: Fallback UTC offset when tzdata is missing. 4, not 5, ON PURPOSE: it
#: reproduces the pre-fix UTC math exactly (09:25 ET == 13:25Z), so a host
#: without tzdata keeps the behaviour we already shipped rather than silently
#: sliding the whole window an hour. Every runner in this estate has tzdata.
_ET_FALLBACK_HOURS = 4

SCHEMA_ID = "marketing.hot_tape/v1"

PACK_REL = "data/marketing/hot_tape_pack.json"
RING_REL = "data/marketing/hot_tape_ring.jsonl"
FIRED_REL = "data/marketing/hot_tape_fired.jsonl"
CONFIG_REL = "config/hot_tape.yml"
#: The earnings calendar the reaction detector keys off. READ BY THE RADAR
#: (scripts/hot_tape_radar.load_earnings, pyarrow) and handed in — this module
#: never opens a parquet, so the detectors stay pure and pandas-free.
EARNINGS_REL = "data/earnings/earnings.parquet"

TRIGGERS: tuple[str, ...] = (
    "sector_rout", "sector_rip", "mover_pop", "mover_drop",
    "threshold_cross", "streak_rarity", "signal_fired", "contrarian_breadth",
    "earnings_reaction", "context_brief",
)

#: This program's name in an outbox item's ``source["lane"]``. Named once
#: because it is a CROSS-MODULE contract, not a local string: packet_to_source
#: stamps it and downstream readers (the radar's carryover sweep, the
#: publisher's orphan-brief gate) select on it. Two lanes — press_lane and
#: fastlane — also stamp ``story_key``, so a reader that drops this filter is
#: reading their rows too.
LANE = "hot_tape"

#: The follow-up trigger (codex two-step publish, §Strongest controlled
#: comparisons): the alert wins speed, the brief wins reposts. Filed by the
#: radar on a LATER tick than the alert it explains, never in the same pass.
BRIEF_TRIGGER = "context_brief"

#: Triggers that describe ONE name's move today, so they share one cooldown
#: memory: an earnings gap is also a |>=4%| move, and the two detectors must
#: not each get a post out of the same tape (one story, one post).
SINGLE_NAME_MOVE_TRIGGERS: tuple[str, ...] = (
    "mover_pop", "mover_drop", "earnings_reaction",
)

#: Market-cap milestones that are worth a wire post when crossed (USD).
MCAP_MILESTONES: tuple[float, ...] = (5e11, 1e12, 2e12, 3e12, 4e12, 5e12)

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

#: In-code defaults. config/hot_tape.yml (written by the radar builder) is
#: deep-merged OVER these, so an absent file leaves a working radar.
DEFAULTS: dict[str, Any] = {
    # ET, not UTC (see the _ET note above): 09:25-16:05 America/New_York is the
    # same five-minutes-of-pre-open-through-five-past-the-close window in both
    # DST regimes, which a UTC pair cannot be.
    "window_et": {"start": "09:25", "end": "16:05"},
    # GitHub's cron is best-effort: a */5 tick regularly lands minutes late, and
    # a tick that arrives at 16:07 ET is still reporting the close. Grace is
    # applied to the END only — waking early is a different question.
    "window_grace_min": 10,
    "max_quote_age_min": 12,
    "bridge_max_gap_days": 1,
    "universe": {
        "min_adv_dollars": 25_000_000,
        "max_tickers": 3000,
        # A record this many weekdays behind the pack's own tip is dead weight,
        # not a laggard: it is dropped from the universe entirely (which is
        # also what removes Polygon's ZAZZT-class test symbols, one of which
        # ranked adv_rank 1 on a $615B fake ADV in the shipped pack).
        "max_lag_weekdays": 10,
    },
    "detectors": {
        "sector": {
            "median_pct": 2.0,
            "breadth": 0.70,
            "min_members": 8,
            # Amendment 2026-07-28: the semis/memory crash the program exists
            # for lives at INDUSTRY granularity ("Semiconductors" -8%) while
            # the parent Finviz sector ("Technology") is masked above -2% by
            # one green mega-cap. Industry groups are smaller, hence a lower
            # member floor.
            "industry_min_members": 5,
        },
        "mover": {
            "min_abs_pct": 4.0,
            "cooldown_min": 120,
            "refire_ratio": 2.0,
            "adv_rank_max": 300,
        },
        "threshold": {
            "min_price": 15.0,
            # FRESHNESS MEMORY (2026-07-31 defect: a dead price phrased as an
            # event). A crossing test here is `prev_close < level <= price` —
            # a condition about the WHOLE DAY, not about this tick — so it
            # stays true from the moment the level is crossed until the close.
            # On 2026-07-29 that shipped "$AAPL right now: just broke below
            # $325.00" at 16:00Z on a level the tape gapped through at the
            # open, ~6.5 hours earlier (the same pass had already said the
            # name was 11% below its all-time high, i.e. nowhere near 325).
            #
            # "Just broke" is licensed by ONE piece of evidence: the same
            # crossing was NOT true at the previous tick. That evidence lives
            # in the ring (`xk` — the crossing ids this lane saw last pass),
            # and it is only trustworthy when the prior row is COMPLETE at or
            # above its own severity floor and recent enough to be "the last
            # tick". Anything else — no ring, a gap in the ring, a crossing
            # below the row's floor — resolves to UNKNOWN, and unknown says
            # "trades below 325", never "just broke below 325".
            #
            # cross_memory_min_severity is what keeps the ledger small: this
            # detector finds ~200-400 crossings a pass across a 900-name plane
            # (measured on the shipped pack: 195 at severity 60, 166 at 70, 34
            # at 80), and the emit path only ever ships the top few by
            # severity. Remembering the 60s would multiply an append-only,
            # 81-commits-a-day ledger by ~10 to license copy no reader ever
            # sees. Lower it (and pay the bytes) if the wire desk starts
            # shipping mid-cap round crosses.
            "cross_memory_min_severity": 80.0,
            "cross_memory_max_ids": 400,
            # How old the prior tick may be and still count as "the last
            # tick". The radar runs */5; 15 minutes tolerates two missed
            # crons before the claim degrades to the standing form.
            "cross_window_min": 15,
        },
        "streak": {"min_len": 5, "min_rarity_days": 365},
        "earnings": {
            # The gap AT the open on a BMO reporter, or the next open after an
            # AH reporter. Same |>=4%| bar as the mover — an earnings day that
            # moves a name less than that is not the reaction anyone is reading.
            "min_abs_pct": 4.0,
            "cooldown_min": 120,
            "refire_ratio": 2.0,
            # How stale the CALENDAR may be. data/earnings/earnings.parquet is
            # forward-looking (it names the NEXT report), so a row only fires
            # when its own as_of is recent: companies move their dates, and a
            # months-old row that still says "reports today, pre-market" would
            # manufacture a reaction post about a company that did not report.
            "max_calendar_age_days": 21,
        },
        "contrarian": {
            "index_pct": -1.5,
            "min_green": 5,
            # Extensions over the spec so neither the index proxy nor the
            # defensive set is a magic constant buried in a detector.
            "index_ticker": "SPY",
            "defensive_sectors": ["Consumer Defensive", "Utilities", "Healthcare"],
        },
    },
    "emit": {
        "max_per_run": 3,
        "max_per_day": 20,
        "flagship_severity_floor": 85,
        "account": "mastermind_news",
        "flagship_account": "flagship",
    },
    # TWO-STEP PUBLISH (codex case study 2026-07-28, §Strongest controlled
    # comparisons A): the one-line flash won ~8% more views; the contextual
    # version won ~9% better interaction efficiency and a ~49% higher
    # repost/view ratio on the SAME story and the SAME account. So both ship:
    # the alert wins speed, the brief wins reposts.
    "two_step": {
        "enabled": True,
        # Only the biggest events earn a second post. 90 is above the flagship
        # mirror floor (85) on purpose — a brief is a bigger commitment than a
        # mirror, not a smaller one.
        "min_severity": 90,
        # The NEXT tick, not this one: the alert must already be out. Raise to
        # 20 to sit inside the masterplan's 20-40 minute band (§10 E1) once the
        # per-trigger engagement table (gate 0.8) says which spacing reposts.
        "delay_min": 5,
        # Past this the moment has passed and a "context brief" is a history
        # lesson. The alert's own carryover window is 20 minutes.
        "max_age_min": 60,
        "max_per_run": 1,
        # The mechanism needs a group to talk about. Fewer live peers than this
        # and we cannot say whether the move is one name or the whole group, so
        # the brief REFUSES rather than guessing.
        "min_peers": 4,
        # |median| of the peer group that makes the move group-wide rather than
        # name-specific. A hypothesis (charter §8), not a constant of nature.
        "group_median_pct": 1.0,
    },
    "demo": {
        "sector_median_pct": 0.5,
        "mover_min_abs_pct": 1.5,
        "earnings_min_abs_pct": 1.5,
        "contrarian_index_pct": -0.3,
        "max_quote_age_min": 100000,
    },
}


def _deep_merge(base: dict, over: dict) -> dict:
    """Recursive dict merge; `over` wins on scalars, dicts merge key-wise."""
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(root: Path | str | None = None) -> dict:
    """config/hot_tape.yml deep-merged over :data:`DEFAULTS`. Never raises."""
    cfg = copy.deepcopy(DEFAULTS)
    try:
        path = Path(root or ".") / CONFIG_REL
        if not path.exists():
            return cfg
        import yaml  # noqa: PLC0415  (lazy — thin lane keeps pyyaml, not pandas)

        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if isinstance(loaded, dict):
            cfg = _deep_merge(cfg, loaded)
    except Exception as exc:  # noqa: BLE001
        log.warning("hot_tape: unreadable %s (%s) - using defaults", CONFIG_REL, exc)
    return cfg


def _c(cfg: dict | None, path: str, default: Any) -> Any:
    """Dotted lookup into cfg with a default. Never raises."""
    node: Any = cfg if isinstance(cfg, dict) else {}
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node if node is not None else default


# ─────────────────────────────────────────────────────────────────────────────
# FactPacket
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class FactPacket:
    """Everything a Hot Tape post is allowed to say, and nothing else.

    ``facts`` is the numeric authority: the wire layer may only render values
    that appear here (masterplan gate 0.3), enforced at runtime by
    :func:`engine.marketing.hot_tape_wire.check_text_numbers`.
    """

    trigger: str
    key: str
    fired_at: str
    session: str
    ticker: str | None
    name: str | None
    sector: str | None
    direction: str
    severity: float
    facts: dict = field(default_factory=dict)
    provenance: dict = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# Time / freshness helpers
# ─────────────────────────────────────────────────────────────────────────────

def _utc(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    return now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)


def _iso(now: datetime | None) -> str:
    return _utc(now).strftime("%Y-%m-%dT%H:%M:%SZ")


def _day(now: datetime | None) -> str:
    return _utc(now).date().isoformat()


def _parse_hhmm(raw: Any, fallback: time) -> time:
    try:
        hh, mm = str(raw).split(":")
        return time(int(hh), int(mm))
    except Exception:  # noqa: BLE001
        return fallback


def _parse_iso_dt(raw: Any) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
    except Exception:  # noqa: BLE001
        return None


def _parse_iso_date(raw: Any) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw)[:10])
    except Exception:  # noqa: BLE001
        return None


def _et_clock(now: datetime | None) -> datetime:
    """`now` read on the US-Eastern wall clock (UTC-4 fallback without tzdata)."""
    t = _utc(now)
    if _ET is not None:
        return t.astimezone(_ET)
    return t - timedelta(hours=_ET_FALLBACK_HOURS)


def _minute_of_day(t: datetime | time) -> float:
    """Wall-clock minutes since midnight, seconds included."""
    return t.hour * 60.0 + t.minute + t.second / 60.0


def in_window(now: datetime | None, cfg: dict | None = None) -> bool:
    """True on an ET weekday inside cfg window_et [start, end + grace].

    The window is evaluated on the EASTERN clock, so it means the same thing in
    March and in December. The end carries ``window_grace_min`` because the
    schedule that drives it is a GitHub cron, which drifts: a 16:03 ET tick that
    lands at 16:07 is still reporting the close, and dropping it silently is how
    a lane loses its last pass of the day.
    """
    try:
        t = _et_clock(now)
        if t.weekday() >= 5:
            return False
        start = _parse_hhmm(_c(cfg, "window_et.start", "09:25"), time(9, 25))
        end = _parse_hhmm(_c(cfg, "window_et.end", "16:05"), time(16, 5))
        try:
            grace = float(_c(cfg, "window_grace_min", DEFAULTS["window_grace_min"]))
        except (TypeError, ValueError):
            grace = float(DEFAULTS["window_grace_min"])
        clock = _minute_of_day(t)
        return _minute_of_day(start) <= clock <= _minute_of_day(end) + max(0.0, grace)
    except Exception as exc:  # noqa: BLE001
        log.warning("hot_tape.in_window failed: %s", exc)
        return False


def session_phase(now: datetime | None = None) -> str:
    """"pre_open" / "rth" / "after_hours" on the ET clock (weekend = after_hours).

    Three phases, not two: the window opens five minutes BEFORE the bell, and a
    09:27 ET post that says "at the close" is a lie about the tape. The copy
    layer keys its live marker off this string (hot_tape_wire._LIVE_MARKERS).
    """
    try:
        t = _et_clock(now)
        if t.weekday() >= 5:
            return "after_hours"
        clock = _minute_of_day(t)
        if clock < _minute_of_day(time(9, 30)):
            return "pre_open"
        return "rth" if clock < _minute_of_day(time(16, 0)) else "after_hours"
    except Exception as exc:  # noqa: BLE001
        log.warning("hot_tape.session_phase failed: %s", exc)
        return "after_hours"


def effective_max_quote_age_min(live: dict | None, cfg: dict | None = None) -> float:
    """The freshness ceiling to judge a quote's ``ts_ms`` against, in minutes.

    ``max_quote_age_min`` (12) is a budget on OBSERVATION LAG — "how long since
    we last looked at the tape". A quote's ``ts_ms`` does not measure that: it is
    Yahoo's ``regularMarketTime``, which is behind wall clock by the observation
    lag PLUS the feed's contractual delay. Measured 2026-07-30T03:46Z on symbols
    trading at the time, that delay is 15.0-15.1 minutes for equities (see
    ``live_verify._feed_delay_min``).

    So a 12-minute budget compared directly against ``ts_ms`` is arithmetically
    unsatisfiable for any equity, on any feed we have, no matter how healthy the
    writer lane is: the freshest US equity quote in a snapshot pushed one second
    ago is already 15 minutes "old" by that measure. That is what kept the P1
    radar at zero events even on the passes whose snapshot WAS current — the
    ``min()`` in :func:`quotes_fresh` passed on a real-time BTC/FX tick, and then
    the radar's per-quote drop discarded the entire equity book behind it.

    The ceiling therefore allows for the delay the feed DECLARES about itself,
    and nothing more. This is not a widened gate — writer-lane staleness is still
    caught with the full 12-minute budget intact on top of the declared delay,
    and the radar separately stands a pass down when the per-quote drop collapses
    the book. Fixture and heatmap-only views declare no delay and keep the bare 12.
    """
    try:
        base = float(_c(cfg, "max_quote_age_min", DEFAULTS["max_quote_age_min"]))
    except (TypeError, ValueError):
        base = float(DEFAULTS["max_quote_age_min"])
    delay = 0.0
    if isinstance(live, dict):
        try:
            delay = max(0.0, float(live.get("feed_delay_min") or 0))
        except (TypeError, ValueError):
            delay = 0.0
    return base + delay


def quotes_fresh(
    live: dict | None,
    now: datetime | None = None,
    cfg: dict | None = None,
) -> tuple[bool, float | None]:
    """(fresh?, freshest quote age in minutes).

    `live` accepts either the :func:`engine.marketing.live_verify.load_live_quotes`
    wrapper ({"quotes": ..., "asof": ...}) or a bare {SYM: quote} map. The age
    reported is the FRESHEST quote's, because one stale symbol in a 2k-symbol
    merge must not stand the whole radar down (the 2026-07-28 tape-gate
    incident was the opposite failure: a stale artifact displacing fresh ones).
    """
    try:
        if not isinstance(live, dict):
            return (False, None)
        quotes = live.get("quotes") if isinstance(live.get("quotes"), dict) else live
        asof_dt = _parse_iso_dt(live.get("asof")) if "quotes" in live else None
        t = _utc(now)
        ages: list[float] = []
        for q in (quotes or {}).values():
            if not isinstance(q, dict):
                continue
            ts_ms = q.get("ts_ms")
            if ts_ms:
                try:
                    dt = datetime.fromtimestamp(float(ts_ms) / 1000.0, tz=timezone.utc)
                    ages.append((t - dt).total_seconds() / 60.0)
                    continue
                except Exception:  # noqa: BLE001
                    pass
        if not ages and asof_dt is not None:
            ages.append((t - asof_dt).total_seconds() / 60.0)
        if not ages:
            return (False, None)
        age = min(ages)
        # Delay-aware ceiling: the budget is on observation lag, the age carries
        # the feed's contractual delay too. See effective_max_quote_age_min.
        max_age = effective_max_quote_age_min(live, cfg)
        return (age <= max_age, round(age, 2))
    except Exception as exc:  # noqa: BLE001
        log.warning("hot_tape.quotes_fresh failed: %s", exc)
        return (False, None)


def _et_date(now: datetime | None) -> date:
    """Today's US-Eastern calendar date (UTC-4 fallback without tzdata)."""
    return _et_clock(now).date()


def _is_session(d: date) -> bool:
    """True when the US cash-equity market holds a session on `d`.

    Weekends AND scheduled NYSE full-day closures. The holiday rules come from
    :mod:`lib.nyse_calendar` — the estate's existing exchange calendar (pure rule
    arithmetic, stdlib only, no data dependency), so there is ONE holiday
    authority and no new dependency. It is imported LAZILY and guarded because
    that module builds a ``ZoneInfo`` at import time, and this one deliberately
    survives a host with no tzdata (see the ``_ET`` note above). A host that
    cannot load the calendar degrades to the old weekday-only answer rather than
    raising: wrong on the ~9 closure days a year, never dead.

    NOT ``collectors.tsa_throughput.us_federal_holidays``: the exchange calendar
    is not the federal one. NYSE closes on Good Friday (not a federal holiday)
    and trades through Columbus Day and Veterans Day (both federal holidays), so
    the federal set is wrong in both directions for a session question.
    """
    if d.weekday() >= 5:
        return False
    try:
        from lib.nyse_calendar import is_session  # noqa: PLC0415

        return bool(is_session(d))
    except Exception:  # pragma: no cover - no tzdata / calendar unavailable
        return True


def _prev_session(d: date) -> date:
    """The trading session before `d` (weekends AND market holidays skipped).

    Used by the earnings detector to name "yesterday's session". Holiday-naive
    weekday arithmetic mislabels the session on every day that follows a
    closure, and the mislabel is silent: an after-hours reporter on Friday
    2026-09-04 is read at Tuesday 2026-09-08's open because Monday is Labor Day,
    but ``d - 1 weekday`` names Monday, ``next_date == yesterday`` never matches,
    and the reaction is simply never detected. Same shape the day after
    Thanksgiving, Good Friday, Juneteenth and Christmas.
    """
    x = d - timedelta(days=1)
    for _ in range(30):          # longest closed stretch is a few days
        if _is_session(x):
            return x
        x -= timedelta(days=1)
    return x


def _sessions_between(older: date, newer: date) -> int:
    """Count trading sessions strictly after `older` up to and including `newer`.

    Sessions, not weekdays: counting a closed Monday as a session makes the
    Tuesday-after-a-holiday pack look two sessions stale when it is in fact
    yesterday's, which suppressed every history fact for a full day after each
    closure (see :func:`bridge_ok`).
    """
    if newer <= older:
        return 0
    n, cursor = 0, older + timedelta(days=1)
    while cursor <= newer:
        if _is_session(cursor):
            n += 1
        cursor += timedelta(days=1)
        if n > 500:                     # runaway guard on a nonsense trade_date
            break
    return n


def bridge_ok(
    pack: dict | None,
    now: datetime | None = None,
    *,
    cfg: dict | None = None,
) -> bool:
    """Is the pack's trade_date adjacent to today's session?

    True when at most ``bridge_max_gap_days`` (default 1) TRADING SESSIONS
    separate the pack's last stored session from today in ET — i.e. a Tuesday
    radar needs Monday's bars, a Monday radar needs Friday's. The store was 18
    sessions stale on 2026-07-28; every history fact is suppressed in that state
    rather than computed against an anchor that is not yesterday.

    Sessions, not weekdays (see :func:`_sessions_between`): the holiday-naive
    count made the day after every closure look one session staler than it was,
    so the Tuesday after Labor Day suppressed all history against a pack that
    genuinely held Friday's — the last session there was.
    """
    try:
        td = _parse_iso_date((pack or {}).get("trade_date"))
        if td is None:
            return False
        today = _et_date(now)
        if td > today:
            return False
        max_gap = int(_c(cfg, "bridge_max_gap_days", DEFAULTS["bridge_max_gap_days"]))
        return _sessions_between(td, today) <= max_gap
    except Exception as exc:  # noqa: BLE001
        log.warning("hot_tape.bridge_ok failed: %s", exc)
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Pack + intraday state (ring, fired)
# ─────────────────────────────────────────────────────────────────────────────

def load_pack(root: Path | str | None = None) -> dict | None:
    """Read data/marketing/hot_tape_pack.json. None when absent/unreadable."""
    try:
        path = Path(root or ".") / PACK_REL
        if not path.exists():
            return None
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else None
    except Exception as exc:  # noqa: BLE001
        log.warning("hot_tape: unreadable pack (%s)", exc)
        return None


def _jsonl():
    """Lazy import of the jsonl helpers (keeps module-level imports stdlib)."""
    from engine.marketing.ledgers import append_jsonl, read_jsonl  # noqa: PLC0415

    return read_jsonl, append_jsonl


def load_ring(root: Path | str | None = None, n: int = 36) -> list[dict]:
    """Last `n` intraday snapshot entries (append-only jsonl)."""
    try:
        read_jsonl, _ = _jsonl()
        rows = read_jsonl(Path(root or ".") / RING_REL)
        return rows[-n:] if n and n > 0 else rows
    except Exception as exc:  # noqa: BLE001
        log.warning("hot_tape.load_ring failed: %s", exc)
        return []


def append_ring(root: Path | str | None, entry: dict) -> None:
    """Append one snapshot entry. Fail-soft."""
    try:
        _, append_jsonl = _jsonl()
        append_jsonl(Path(root or ".") / RING_REL, entry)
    except Exception as exc:  # noqa: BLE001
        log.warning("hot_tape.append_ring failed: %s", exc)


def compact_ring(root: Path | str | None = None, keep: int = 36) -> None:
    """Rewrite the ring keeping only the last `keep` entries.

    Call this only when the OLDEST entry is from a previous day: rewriting a
    same-day ring throws away the intraday history the "$X added in 3 hours"
    claims (masterplan T6) are built from.
    """
    try:
        path = Path(root or ".") / RING_REL
        read_jsonl, _ = _jsonl()
        rows = read_jsonl(path)
        if len(rows) <= keep:
            return
        tail = rows[-keep:] if keep > 0 else []
        body = "".join(
            json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n" for r in tail
        )
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(body, encoding="utf-8")
        tmp.replace(path)
    except Exception as exc:  # noqa: BLE001
        log.warning("hot_tape.compact_ring failed: %s", exc)


def load_fired(root: Path | str | None = None, day: str | None = None) -> list[dict]:
    """Fired-event rows for `day` (UTC date iso; default today)."""
    try:
        target = day or _day(None)
        read_jsonl, _ = _jsonl()
        rows = read_jsonl(Path(root or ".") / FIRED_REL)
        return [
            r for r in rows
            if str(r.get("day") or str(r.get("fired_at") or "")[:10]) == target
        ]
    except Exception as exc:  # noqa: BLE001
        log.warning("hot_tape.load_fired failed: %s", exc)
        return []


def append_fired(root: Path | str | None, entry: dict) -> None:
    """Append one fired-event row (cooldown/dedupe memory). Fail-soft."""
    try:
        row = dict(entry or {})
        row.setdefault("day", str(row.get("fired_at") or _iso(None))[:10])
        _, append_jsonl = _jsonl()
        append_jsonl(Path(root or ".") / FIRED_REL, row)
    except Exception as exc:  # noqa: BLE001
        log.warning("hot_tape.append_fired failed: %s", exc)


def fired_entry(packet: FactPacket, *, item_id: str | None, account: str) -> dict:
    """Build the fired-ledger row for a packet that was emitted.

    ``severity`` rides along so the two-step publish loop can decide whether an
    alert earned a follow-up brief WITHOUT re-reading the outbox: the fired
    ledger is already this lane's dedupe memory, and one read per pass is the
    budget an 81-runs-a-day loop has.
    """
    return {
        "key": packet.key,
        "trigger": packet.trigger,
        "ticker": packet.ticker,
        "sector": packet.sector,
        "direction": packet.direction,
        "magnitude": _magnitude(packet),
        "severity": float(packet.severity),
        "fired_at": packet.fired_at,
        "day": str(packet.fired_at)[:10],
        "item_id": item_id,
        "account": account,
        "demo": bool((packet.provenance or {}).get("demo")),
    }


def _magnitude(packet: FactPacket) -> float | None:
    """The headline % this packet claims (cooldown memory + emit ordering).

    Also copied to ``source.baseline_pct`` for provenance/parity — see
    :func:`packet_to_source` on what the post-time gate does and does not do
    with it.
    """
    f = packet.facts or {}
    for k in ("pct", "median_pct", "pct_today", "index_pct"):
        v = f.get(k)
        if isinstance(v, (int, float)):
            return float(v)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Detector helpers
# ─────────────────────────────────────────────────────────────────────────────

def _num(v: Any) -> float | None:
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        try:
            f = float(v)
        except Exception:  # noqa: BLE001
            return None
        return f if f == f and abs(f) != float("inf") else None
    return None


def _r2(v: Any) -> float | None:
    n = _num(v)
    return None if n is None else round(n, 2)


def _tile_pct(tile: dict, quotes: dict) -> float | None:
    """Live change_pct for a heatmap tile, falling back to the tile's own 1D."""
    sym = str(tile.get("t") or "").upper()
    q = quotes.get(sym) if sym else None
    if isinstance(q, dict):
        live = _num(q.get("change_pct"))
        if live is not None:
            return live
    perf = tile.get("perf")
    return _num(perf.get("1D")) if isinstance(perf, dict) else None


def _pack_rec(pack: dict | None, sym: str) -> dict:
    try:
        rec = ((pack or {}).get("tickers") or {}).get(sym)
        return rec if isinstance(rec, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _rec_is_current(rec: dict | None, pack: dict | None) -> bool:
    """Does THIS record's last bar sit on the pack's own tip?

    :func:`bridge_ok` is a GLOBAL verdict about the store; it says nothing about
    an individual name. The shipped pack carried 26 live-quoted records lagging
    its tip — one of them a 5-day "streak" that had ended six sessions earlier,
    which would have posted as "Day 6 of the slide" off a bridge that was
    perfectly fine. History facts need BOTH gates.
    """
    tip = (pack or {}).get("trade_date")
    return bool(tip) and (rec or {}).get("last_date") == tip


def _history_ok(rec: dict | None, pack: dict | None, bridged: bool) -> bool:
    """The full history gate: global bridge, no split suspicion, record current."""
    return (bool(bridged)
            and not bool((rec or {}).get("suspect"))
            and _rec_is_current(rec, pack))


def _attention_boost(rec: dict) -> float:
    """Shared severity boost: index membership, liquidity rank, size."""
    boost = 0.0
    if rec.get("sp500"):
        boost += 10.0
    rank = _num(rec.get("adv_rank"))
    if rank is not None and rank <= 100:
        boost += 10.0
    mcap = _num(rec.get("mcap_usd"))
    if mcap is not None and mcap >= 1e11:
        boost += 10.0
    return boost


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return round(max(lo, min(hi, v)), 2)


def _fired_keys(fired_today: list[dict] | None) -> set[str]:
    return {str(r.get("key")) for r in (fired_today or []) if r.get("key")}


def _provenance(
    pack: dict | None,
    quotes_asof: Any,
    quote: dict | None,
    bridged: bool,
    demo: bool,
) -> dict:
    return {
        "pack_asof": (pack or {}).get("built_at"),
        "store_last_date": (pack or {}).get("trade_date"),
        "quotes_asof": quotes_asof,
        "quote_ts_ms": (quote or {}).get("ts_ms"),
        "quote_source": (quote or {}).get("source"),
        "bridge_ok": bool(bridged),
        "demo": bool(demo),
    }


def _move_priors(fired_today: list[dict] | None, sym: str, direction: str) -> list[dict]:
    """Today's already-fired single-name MOVE rows for `sym` in `direction`.

    Shared by the mover and earnings detectors so the two cannot each hand out
    a post for the same tape (:data:`SINGLE_NAME_MOVE_TRIGGERS`).
    """
    return [
        r for r in (fired_today or [])
        if str(r.get("ticker") or "").upper() == sym
        and str(r.get("direction")) == direction
        and str(r.get("trigger") or "") in SINGLE_NAME_MOVE_TRIGGERS
    ]


def _rsi_step(rec: dict, delta: float) -> float | None:
    """One Wilder step from the pack's stored average gain/loss."""
    ag, al = _num(rec.get("rsi_avg_gain")), _num(rec.get("rsi_avg_loss"))
    if ag is None or al is None:
        return None
    period = 14.0
    gain = max(delta, 0.0)
    loss = max(-delta, 0.0)
    ag2 = (ag * (period - 1) + gain) / period
    al2 = (al * (period - 1) + loss) / period
    if al2 <= 0:
        return 100.0 if ag2 > 0 else 50.0
    rs = ag2 / al2
    return round(100.0 - (100.0 / (1.0 + rs)), 2)


# ─────────────────────────────────────────────────────────────────────────────
# Detectors
# ─────────────────────────────────────────────────────────────────────────────

def _detect_group_moves(
    quotes: dict,
    pack: dict | None,
    heatmap: dict | None,
    fired: set[str],
    now: datetime,
    cfg: dict,
    demo: bool,
    bridged: bool,
    quotes_asof: Any,
) -> list[FactPacket]:
    """sector_rout / sector_rip over BOTH heatmap sector and industry groups.

    Amendment 2026-07-28 (verified against that day's closing tape): grouping
    by Finviz sector alone never fires on the day this program exists for.
    "Technology" held above -2% while its "Semiconductors" industry printed a
    -8% median. Both granularities are scanned; when an industry and its parent
    sector both qualify only the more extreme one is emitted, because two
    overlapping list posts in one sweep read as spam.
    """
    out: list[FactPacket] = []
    tiles = [t for t in ((heatmap or {}).get("tiles") or []) if isinstance(t, dict)]
    if not tiles:
        return out

    thresh = float(
        _c(cfg, "demo.sector_median_pct", DEFAULTS["demo"]["sector_median_pct"]) if demo
        else _c(cfg, "detectors.sector.median_pct", 2.0)
    )
    breadth_min = float(_c(cfg, "detectors.sector.breadth", 0.70))
    min_sector = int(_c(cfg, "detectors.sector.min_members", 8))
    min_industry = int(_c(cfg, "detectors.sector.industry_min_members", 5))
    index_sym = str(_c(cfg, "detectors.contrarian.index_ticker", "SPY")).upper()
    index_pct = _r2((quotes.get(index_sym) or {}).get("change_pct"))
    day = _day(now)

    groups: dict[tuple[str, str], list[dict]] = {}
    parent_of: dict[str, str] = {}
    for tile in tiles:
        sector = str(tile.get("sector") or "").strip()
        industry = str(tile.get("industry") or "").strip()
        if sector:
            groups.setdefault(("sector", sector), []).append(tile)
        if industry:
            groups.setdefault(("industry", industry), []).append(tile)
            if sector:
                parent_of[industry] = sector

    candidates: dict[tuple[str, str], FactPacket] = {}
    #: (kind, label) -> members whose mcap the pack could not supply. Keyed by
    #: the PAIR because a sector and an industry may share a label and they are
    #: different groups. Collected here and annotated ONCE below, for the groups
    #: that actually emit: this runs 81 times a day over every sector AND
    #: industry, and a per-group warning on every pass is a console nobody reads.
    dropped_dollars: dict[tuple[str, str], list[str]] = {}
    for (kind, label), members in sorted(groups.items()):
        floor = min_industry if kind == "industry" else min_sector
        pcts: list[tuple[str, float]] = []
        for tile in members:
            pct = _tile_pct(tile, quotes)
            sym = str(tile.get("t") or "").upper()
            if pct is not None and sym:
                pcts.append((sym, pct))
        if len(pcts) < floor:
            continue
        median = statistics.median([p for _, p in pcts])
        if median <= -thresh:
            direction, trigger = "down", "sector_rout"
        elif median >= thresh:
            direction, trigger = "up", "sector_rip"
        else:
            continue
        agree = [p for _, p in pcts if (p < 0 if direction == "down" else p > 0)]
        breadth = len(agree) / float(len(pcts))
        if breadth < breadth_min:
            continue

        key = f"sector:{label}:{direction}:{day}"
        # NOTE: the fired-key filter deliberately does NOT run here. It runs
        # AFTER the industry/parent overlap suppression below — filtering
        # during the build removes the fired winner from the overlap contest,
        # so its already-covered rival (the same names at the other
        # granularity) would sail out five minutes later as a "new" story.
        # Build everything, pick winners, THEN drop what already fired.

        ordered = sorted(pcts, key=lambda kv: kv[1], reverse=(direction == "up"))
        leaders = [[s, round(p, 2)] for s, p in ordered[:5]]

        dollars: float | None = None
        missing_mcap: list[str] = []
        acc = 0.0
        for sym, pct in pcts:
            mcap = _num(_pack_rec(pack, sym).get("mcap_usd"))
            if mcap is None:
                missing_mcap.append(sym)
                continue
            acc += mcap * pct / 100.0
        # EVERY MEMBER OR NO DOLLARS (2026-07-31 defect; was a 70% coverage
        # floor). The old gate let up to 30% of a group's members fall out of
        # the sum with no trace, and the shipped result is a figure that moves
        # against its own tape: the same industry, the same five names, the
        # same session printed "median +11.8% ... roughly $148 billion in fresh
        # market value" at 15:27 and "median +13.4% ... roughly $135 billion"
        # at 19:03. A reader can only conclude one of the two numbers is wrong;
        # in fact both were "right" over silently different member sets.
        #
        # With full coverage the base is pinned by construction — mcap_usd is a
        # nightly pack field, constant through the session — so the sum is a
        # fixed-weight function of the moves and CANNOT shrink while the moves
        # grow. That is the property the copy implies, so it is the property
        # the fact must have. A missing cap now kills the dollar claim and is
        # COUNTED (facts.dollar_missing_caps + the annotation below): the
        # fail-open-hides-a-probe-crash law says a total that can quietly lose
        # a member is worse than no total, and the copy already has a leaders
        # fallback for exactly this.
        #
        # SIGN GUARD (reviewer M8), unchanged. The aggregate is a cap-WEIGHTED
        # sum while the trigger is a MEDIAN, so one green mega-cap can flip the
        # net positive inside a group the median calls a rout. "$41 billion
        # gone" rendered off a +$41B aggregate is a lie with a minus sign glued
        # on; when the sign disagrees with the direction we have no dollar
        # translation either.
        if (pcts and not missing_mcap
                and (direction == "down") == (acc < 0)):
            dollars = round(acc)
        if missing_mcap:
            dropped_dollars[(kind, label)] = list(missing_mcap)

        facts: dict[str, Any] = {
            "sector": label,
            "group_kind": kind,
            "median_pct": round(median, 2),
            "breadth_pct": round(breadth * 100.0, 2),
            "n_members": len(pcts),
            ("n_down" if direction == "down" else "n_up"): len(agree),
            "leaders": leaders,
            "dollar_moved_usd": dollars,
            # The counted tally. A number nobody can see is how a silently
            # shrinking sum survived: this one rides on the packet, into the
            # outbox item's source block, where a post-mortem can read it.
            "dollar_missing_caps": len(missing_mcap),
            "index_pct": index_pct,
        }
        packet = FactPacket(
            trigger=trigger,
            key=key,
            fired_at=_iso(now),
            session=session_phase(now),
            ticker=None,
            name=None,
            sector=label,
            direction=direction,
            severity=_clamp(80.0 + min(10.0, abs(median) * 2.0)),
            facts=facts,
            provenance=_provenance(pack, quotes_asof, None, bridged, demo),
        )
        candidates[(kind, label)] = packet

    # Overlap preference: an industry and its parent sector are one story.
    suppressed: set[tuple[str, str]] = set()
    for (kind, label), packet in candidates.items():
        if kind != "industry":
            continue
        parent = parent_of.get(label)
        rival = candidates.get(("sector", parent)) if parent else None
        if rival is None:
            continue
        mine = abs(_num(packet.facts.get("median_pct")) or 0.0)
        theirs = abs(_num(rival.facts.get("median_pct")) or 0.0)
        suppressed.add(("sector", parent) if mine > theirs else (kind, label))

    # Fired-key filter LAST (see the note at the key build above): the overlap
    # contest must see every candidate, including ones that already fired, or
    # a fired industry's parent sector re-emits the same names next pass.
    out.extend(p for k, p in candidates.items()
               if k not in suppressed and p.key not in fired)

    # THE LOST MEMBER HAS TO BE AUDIBLE. A dropped dollar claim is a quality
    # regression with a cause (a pack record with no mcap_usd), and the cause
    # is fixable in the nightly builder — but only by someone who can see it.
    # Bare print, line start, flushed: this module runs inside the radar's
    # Actions step and every logger here prefixes, which GitHub then drops.
    for packet in out:
        names_missing = dropped_dollars.get(
            (str(packet.facts.get("group_kind") or ""), str(packet.sector or "")))
        if not names_missing:
            continue
        print(f"::warning title=hot-tape-group-dollars-dropped::"
              f"{packet.sector}: {len(names_missing)} of "
              f"{packet.facts.get('n_members')} members have no mcap_usd in the "
              f"pack ({', '.join(sorted(names_missing)[:8])}) - the dollar "
              f"translation is withheld rather than summed over a silently "
              f"smaller group", flush=True)
    return out


def _detect_movers(
    quotes: dict,
    pack: dict | None,
    heatmap: dict | None,
    fired_today: list[dict],
    now: datetime,
    cfg: dict,
    demo: bool,
    bridged: bool,
    quotes_asof: Any,
) -> list[FactPacket]:
    """mover_pop / mover_drop on the attention universe (§2 T1)."""
    out: list[FactPacket] = []
    min_abs = float(
        _c(cfg, "demo.mover_min_abs_pct", DEFAULTS["demo"]["mover_min_abs_pct"]) if demo
        else _c(cfg, "detectors.mover.min_abs_pct", 4.0)
    )
    cooldown = float(_c(cfg, "detectors.mover.cooldown_min", 120))
    refire = float(_c(cfg, "detectors.mover.refire_ratio", 2.0))
    rank_max = float(_c(cfg, "detectors.mover.adv_rank_max", 300))
    day = _day(now)

    names: dict[str, str] = {}
    universe: set[str] = set()
    for tile in ((heatmap or {}).get("tiles") or []):
        if not isinstance(tile, dict):
            continue
        sym = str(tile.get("t") or "").upper()
        if sym:
            universe.add(sym)
            if tile.get("name"):
                names[sym] = str(tile["name"])
    for sym, rec in ((pack or {}).get("tickers") or {}).items():
        rank = _num((rec or {}).get("adv_rank"))
        if rank is not None and rank <= rank_max:
            universe.add(str(sym).upper())

    for sym in sorted(universe):
        quote = quotes.get(sym)
        if not isinstance(quote, dict):
            continue
        pct = _num(quote.get("change_pct"))
        if pct is None or abs(pct) < min_abs:
            continue
        direction = "up" if pct > 0 else "down"
        trigger = "mover_pop" if direction == "up" else "mover_drop"

        # ONE COOLDOWN MEMORY PER NAME PER DIRECTION, shared with the earnings
        # detector: an earnings gap IS a |>=4%| move, so a name that already got
        # its earnings-reaction post must not get a second one as a "mover"
        # five minutes later.
        priors = _move_priors(fired_today, sym, direction)
        k = len(priors)
        if priors:
            last = max(priors, key=lambda r: str(r.get("fired_at") or ""))
            when = _parse_iso_dt(last.get("fired_at"))
            prior_mag = abs(_num(last.get("magnitude")) or 0.0)
            within = when is not None and (now - when).total_seconds() / 60.0 < cooldown
            if within and (prior_mag <= 0 or abs(pct) < refire * prior_mag):
                continue

        rec = _pack_rec(pack, sym)
        price = _num(quote.get("price"))
        prev_close = _num(quote.get("prev_close"))
        history = _history_ok(rec, pack, bridged)

        facts: dict[str, Any] = {
            "ticker": sym,
            "name": names.get(sym) or None,
            "pct": round(pct, 2),
            "price": _r2(price),
            "prev_close": _r2(prev_close),
            "dollar_delta_usd": None,
            "pct_from_ath_live": None,
            "ath": None,
            "ath_date": None,
            "streak_extends": None,
            "rsi_live": None,
            "rsi_band": None,
            "rsi_since": None,
            "biggest_1d": None,
            "sector": rec.get("sector") or None,
            "earn_next_date": rec.get("earn_next_date") or None,
            "earn_next_time": rec.get("earn_next_time") or None,
        }

        mcap = _num(rec.get("mcap_usd"))
        if mcap is not None:
            facts["dollar_delta_usd"] = round(mcap * pct / 100.0)

        ath = _num(rec.get("ath"))
        if history and price is not None and ath is not None and ath > 0:
            facts["pct_from_ath_live"] = round((price - ath) / ath * 100.0, 2)
            facts["ath"] = round(ath, 2)
            facts["ath_date"] = rec.get("ath_date")

        streak = rec.get("streak") if isinstance(rec.get("streak"), dict) else {}
        s_dir, s_len = streak.get("dir"), _num(streak.get("len"))
        if history and s_dir == direction and s_len is not None:
            len_today = int(s_len) + 1
            since = (streak.get("last_run_ge") or {}).get(str(len_today))
            facts["streak_extends"] = {
                "dir": direction,
                "len_today": len_today,
                "since": since,
                "window_start": rec.get("window_start"),
            }

        anchor = _num(rec.get("last_close"))
        if history and price is not None and anchor is not None:
            rsi_live = _rsi_step(rec, price - anchor)
            if rsi_live is not None:
                facts["rsi_live"] = rsi_live
                # A BAND FACT IS A CROSSING THAT HAPPENED TODAY, never a state
                # (reviewer C2). The old test was "rsi_live is past the band",
                # which fired on continuation: a name that closed at RSI 75 and
                # kept climbing got "RSI is back above 70 for the first time
                # since <date>" — it never left. Worse, the side came from the
                # DIRECTION, so a name selling off from 78 to 75.3 rendered
                # "back under 70" at an RSI of 75.3. Both legs are now pinned:
                # yesterday's stored rsi14 must be on the OTHER side of the
                # band, and the direction must agree with the crossing.
                rsi_prev = _num(rec.get("rsi14"))
                if (direction == "down" and rsi_live <= 30.0
                        and rsi_prev is not None and rsi_prev > 30.0
                        and rec.get("last_rsi_le_30")):
                    facts["rsi_band"] = 30
                    facts["rsi_since"] = rec.get("last_rsi_le_30")
                elif (direction == "up" and rsi_live >= 70.0
                      and rsi_prev is not None and rsi_prev < 70.0
                      and rec.get("last_rsi_ge_70")):
                    facts["rsi_band"] = 70
                    facts["rsi_since"] = rec.get("last_rsi_ge_70")

        if history:
            extreme = rec.get("max_up_1d") if direction == "up" else rec.get("max_dn_1d")
            prior_pct = _num((extreme or {}).get("pct")) if isinstance(extreme, dict) else None
            if prior_pct is not None and abs(pct) > abs(prior_pct):
                facts["biggest_1d"] = {
                    "window_start": rec.get("window_start"),
                    "prior_pct": round(prior_pct, 2),
                    "prior_date": (extreme or {}).get("date"),
                }

        severity = min(70.0, 50.0 + 5.0 * max(0.0, abs(pct) - 4.0)) + _attention_boost(rec)
        out.append(FactPacket(
            trigger=trigger,
            key=f"mover:{sym}:{direction}:{day}:{k}",
            fired_at=_iso(now),
            session=session_phase(now),
            ticker=sym,
            name=names.get(sym) or None,
            sector=rec.get("sector") or None,
            direction=direction,
            severity=_clamp(severity),
            facts=facts,
            provenance=_provenance(pack, quotes_asof, quote, bridged, demo),
        ))
    return out


def _parse_report_date(raw: Any) -> date | None:
    """A surprises_json ``reported`` stamp -> date. ISO first, then US M/D/YYYY.

    The vendor writes "4/30/2026"; the rest of this estate writes ISO. Both are
    accepted and anything else is None, because a report date we cannot read is
    a report we cannot claim happened.
    """
    iso = _parse_iso_date(raw)
    if iso is not None:
        return iso
    try:
        month, day, year = str(raw).strip().split("/")
        return date(int(year), int(month), int(day))
    except Exception:  # noqa: BLE001
        return None


def _fresh_surprise(rows: Any, report_date: date) -> dict | None:
    """The EPS beat/miss device, but ONLY when it is about THIS report.

    ``surprises_json`` is a history, newest first. Its head is the fresh row
    only when the vendor has already filed the quarter we just detected — a BMO
    reporter usually has not been filed by 09:30, so that post ships with its
    other devices and no EPS line rather than with LAST quarter's numbers
    presented as today's.
    """
    if not isinstance(rows, list) or not rows:
        return None
    head = rows[0] if isinstance(rows[0], dict) else None
    if not head:
        return None
    when = _parse_report_date(head.get("reported"))
    if when is None or when != report_date:
        return None
    actual, consensus = _num(head.get("eps")), _num(head.get("consensus"))
    if actual is None or consensus is None:
        return None
    return {
        "actual": round(actual, 2),
        "consensus": round(consensus, 2),
        "surprise_pct": _r2(head.get("surprise_pct")),
        "reported": when.isoformat(),
        "beat": bool(actual >= consensus),
    }


def _detect_earnings(
    quotes: dict,
    pack: dict | None,
    heatmap: dict | None,
    earnings: dict | None,
    fired_today: list[dict],
    now: datetime,
    cfg: dict,
    demo: bool,
    bridged: bool,
    quotes_asof: Any,
) -> list[FactPacket]:
    """earnings_reaction: the gap a report opened (§2 T4, masterplan §10 E1).

    TWO SHAPES, ONE DETECTOR, because we have no extended-hours quotes yet
    (masterplan §4, "PHASE 2"):

      * **BMO** — the calendar says this name reports TODAY, pre-market, so the
        move we can see at the open IS the reaction.
      * **AH** — the calendar says it reported after the PREVIOUS session's
        close, so today's open is the reaction.

    The calendar is forward-looking, so a row is only trusted while its own
    ``as_of`` is fresh (``detectors.earnings.max_calendar_age_days``): companies
    move their dates, and a months-old "reports today" row would manufacture a
    reaction post about a company that did not report.

    GATE 0.2 IS ENFORCED IN THE DETECTOR, not only in the copy layer: a packet
    with no EPS surprise, no dollar translation and no history fact carries no
    differentiating stat, so it is never built — which also saves the Chrome
    raster and the R2 upload its card would have cost.
    """
    out: list[FactPacket] = []
    rows = (earnings or {}).get("tickers")
    if not isinstance(rows, dict) or not rows:
        return out

    prod_min = float(_c(cfg, "detectors.earnings.min_abs_pct", 4.0))
    min_abs = float(
        _c(cfg, "demo.earnings_min_abs_pct", DEFAULTS["demo"]["earnings_min_abs_pct"])
        if demo else prod_min
    )
    cooldown = float(_c(cfg, "detectors.earnings.cooldown_min", 120))
    refire = float(_c(cfg, "detectors.earnings.refire_ratio", 2.0))
    max_cal_age = int(_c(cfg, "detectors.earnings.max_calendar_age_days", 21))
    day = _day(now)
    today = _et_date(now)
    yesterday = _prev_session(today)
    view_asof = (earnings or {}).get("asof")
    names = {
        str(t.get("t") or "").upper(): str(t.get("name") or "")
        for t in ((heatmap or {}).get("tiles") or []) if isinstance(t, dict)
    }

    for raw_sym in sorted(rows):
        row = rows.get(raw_sym)
        if not isinstance(row, dict):
            continue
        sym = str(raw_sym).upper()
        next_date = _parse_iso_date(row.get("next_date"))
        next_time = str(row.get("next_time") or "").strip().lower()
        if next_date == today and "pre-market" in next_time:
            when, report_date = "bmo", today
        elif next_date == yesterday and "after-hours" in next_time:
            when, report_date = "ah", yesterday
        else:
            continue

        cal_asof = _parse_iso_date(row.get("as_of") or view_asof)
        if cal_asof is None or (today - cal_asof).days > max_cal_age:
            continue

        quote = quotes.get(sym)
        if not isinstance(quote, dict):
            continue
        pct = _num(quote.get("change_pct"))
        if pct is None or abs(pct) < min_abs:
            continue
        direction = "up" if pct > 0 else "down"

        priors = _move_priors(fired_today, sym, direction)
        k = len(priors)
        if priors:
            last = max(priors, key=lambda r: str(r.get("fired_at") or ""))
            fired_at = _parse_iso_dt(last.get("fired_at"))
            prior_mag = abs(_num(last.get("magnitude")) or 0.0)
            within = (fired_at is not None
                      and (now - fired_at).total_seconds() / 60.0 < cooldown)
            if within and (prior_mag <= 0 or abs(pct) < refire * prior_mag):
                continue

        rec = _pack_rec(pack, sym)
        price = _num(quote.get("price"))
        prev_close = _num(quote.get("prev_close"))
        history = _history_ok(rec, pack, bridged)

        facts: dict[str, Any] = {
            "ticker": sym,
            "name": names.get(sym) or None,
            "pct": round(pct, 2),
            "price": _r2(price),
            "prev_close": _r2(prev_close),
            "report_when": when,
            "report_date": report_date.isoformat(),
            "earn_next_time": row.get("next_time") or None,
            "eps": _fresh_surprise(row.get("surprises"), report_date),
            "dollar_delta_usd": None,
            "pct_from_ath_live": None,
            "ath": None,
            "ath_date": None,
            "biggest_1d": None,
            "sector": rec.get("sector") or None,
        }

        mcap = _num(rec.get("mcap_usd"))
        if mcap is not None:
            facts["dollar_delta_usd"] = round(mcap * pct / 100.0)

        ath = _num(rec.get("ath"))
        if history and price is not None and ath is not None and ath > 0:
            facts["pct_from_ath_live"] = round((price - ath) / ath * 100.0, 2)
            facts["ath"] = round(ath, 2)
            facts["ath_date"] = rec.get("ath_date")

        if history:
            extreme = rec.get("max_up_1d") if direction == "up" else rec.get("max_dn_1d")
            prior_pct = (_num((extreme or {}).get("pct"))
                         if isinstance(extreme, dict) else None)
            if prior_pct is not None and abs(pct) > abs(prior_pct):
                facts["biggest_1d"] = {
                    "window_start": rec.get("window_start"),
                    "prior_pct": round(prior_pct, 2),
                    "prior_date": (extreme or {}).get("date"),
                }

        # GATE 0.2 IN THE DETECTOR, and it must match what the WIRE can actually
        # render — not merely "some history exists". The mover twin has already
        # been suppressed by the time compose_wire runs, so a packet that passes
        # a loose gate here and then refuses downstream costs BOTH posts. The
        # conditions below are _eps_clause / _dollar_clause / _record_rank_clause
        # read back exactly (the -5% floor included).
        from_ath = facts["pct_from_ath_live"]
        has_record = bool(facts["biggest_1d"]) or (
            from_ath is not None and from_ath <= -5.0
            and facts["ath"] is not None and facts["ath_date"])
        if not (facts["eps"] or facts["dollar_delta_usd"] is not None or has_record):
            log.info("hot_tape: earnings reaction for %s has no device slot - refused", sym)
            continue

        severity = (min(80.0, 60.0 + 4.0 * max(0.0, abs(pct) - prod_min))
                    + _attention_boost(rec))
        out.append(FactPacket(
            trigger="earnings_reaction",
            key=f"earnings:{sym}:{direction}:{day}:{k}",
            fired_at=_iso(now),
            session=session_phase(now),
            ticker=sym,
            name=names.get(sym) or None,
            sector=rec.get("sector") or None,
            direction=direction,
            severity=_clamp(severity),
            facts=facts,
            provenance=_provenance(pack, quotes_asof, quote, bridged, demo),
        ))
    return out


#: Ring-row keys carrying this lane's threshold freshness memory. Named once
#: because they are a CROSS-MODULE contract: :func:`cross_memory_row` writes
#: them from the radar's ring entry and :func:`_prior_cross_state` reads them
#: back on the next tick. A row missing them is not "no crossings last tick",
#: it is "we do not know" — see the fail-closed note in _prior_cross_state.
RING_CROSS_IDS = "xk"
RING_CROSS_COMPLETE = "xk_full"
RING_CROSS_MIN_SEV = "xk_min_sev"

#: What the freshness gate concluded, stamped on every threshold packet so a
#: post-mortem can tell a soft claim caused by an old crossing apart from one
#: caused by a missing memory. Only ``first_seen`` licenses "just broke".
CROSS_FIRST_SEEN = "first_seen"
CROSS_EARLIER = "earlier"
CROSS_UNKNOWN = "unknown"


def _cross_id(sym: Any, kind: Any, level: Any) -> str:
    """The day-scoped identity of ONE level crossing (ring memory key).

    Deliberately NOT the fired key: that one carries the date, and the ring row
    already carries its own day. Short because it is written ~34-400 times a
    row, 81 rows a day, into an append-only ledger that is committed.
    """
    return f"{str(sym).upper()}:{kind}:{level}"


def cross_memory_row(events: list[FactPacket] | None, cfg: dict | None = None) -> dict:
    """The freshness-memory block for THIS pass's ring row.

    The radar folds this into its snapshot entry so the NEXT pass can tell a
    level crossed five minutes ago from one crossed at the opening bell. See
    the ``cross_memory_min_severity`` note in DEFAULTS for why this is a floor
    and not the whole crossing set.

    ``xk_full`` is the load-bearing field: it says "this list is COMPLETE at or
    above ``xk_min_sev``". Without it a truncated list would read as "that
    crossing was not there last tick", which is exactly the false "just broke"
    this memory exists to prevent.
    """
    floor = float(_c(cfg, "detectors.threshold.cross_memory_min_severity", 80.0))
    cap = int(_c(cfg, "detectors.threshold.cross_memory_max_ids", 400))
    ids: list[str] = []
    for packet in (events or []):
        if getattr(packet, "trigger", "") != "threshold_cross":
            continue
        cross_id = str((getattr(packet, "facts", {}) or {}).get("cross_id") or "")
        if cross_id and float(getattr(packet, "severity", 0.0) or 0.0) >= floor:
            ids.append(cross_id)
    ids = sorted(set(ids))
    complete = len(ids) <= cap
    return {
        RING_CROSS_IDS: ids[:cap],
        RING_CROSS_COMPLETE: complete,
        RING_CROSS_MIN_SEV: floor,
    }


def _prior_cross_state(
    ring: list[dict] | None, now: datetime, cfg: dict | None
) -> dict | None:
    """What the PREVIOUS tick knew about level crossings, or None for unknown.

    Returns ``{"ids": set[str], "at": iso, "min_sev": float}``.

    FAIL CLOSED, EVERY BRANCH. None is returned when there is no ring, when the
    newest same-day row is not ours to trust (no memory block, an incomplete
    one), or when it is older than ``cross_window_min`` — because in all of
    those cases "the crossing is absent from the prior tick" means nothing, and
    reading absence as freshness is the defect (a missed cron would turn every
    hours-old level into "just broke"). The caller degrades to the standing
    phrasing, which is always true.
    """
    rows = [r for r in (ring or []) if isinstance(r, dict)]
    if not rows:
        return None
    day = _day(now)
    same_day = [r for r in rows
                if str(r.get("day") or str(r.get("at") or "")[:10]) == day]
    if not same_day:
        return None
    row = same_day[-1]
    if not bool(row.get(RING_CROSS_COMPLETE)):
        return None
    at = _parse_iso_dt(row.get("at"))
    if at is None:
        return None
    window = float(_c(cfg, "detectors.threshold.cross_window_min", 15))
    age_min = (_utc(now) - at).total_seconds() / 60.0
    if age_min < 0 or age_min > window:
        return None
    ids = {str(x) for x in (row.get(RING_CROSS_IDS) or []) if x}
    return {"ids": ids, "at": str(row.get("at") or ""),
            "min_sev": float(_num(row.get(RING_CROSS_MIN_SEV)) or 0.0)}


def _detect_thresholds(
    quotes: dict,
    pack: dict | None,
    heatmap: dict | None,
    fired: set[str],
    now: datetime,
    cfg: dict,
    demo: bool,
    bridged: bool,
    quotes_asof: Any,
    ring: list[dict] | None = None,
) -> list[FactPacket]:
    """threshold_cross: correction / bear / new ATH / round number / mcap (§2 T2)."""
    out: list[FactPacket] = []
    min_price = float(_c(cfg, "detectors.threshold.min_price", 15.0))
    prior = _prior_cross_state(ring, now, cfg)
    day = _day(now)
    names = {
        str(t.get("t") or "").upper(): str(t.get("name") or "")
        for t in ((heatmap or {}).get("tiles") or []) if isinstance(t, dict)
    }

    for sym, rec in sorted(((pack or {}).get("tickers") or {}).items()):
        sym = str(sym).upper()
        quote = quotes.get(sym)
        if not isinstance(quote, dict) or not isinstance(rec, dict):
            continue
        price, prev = _num(quote.get("price")), _num(quote.get("prev_close"))
        if price is None or prev is None:
            continue
        history = _history_ok(rec, pack, bridged)
        ath, ath_date = _num(rec.get("ath")), rec.get("ath_date")
        found: list[tuple[str, Any, str, dict]] = []

        if history and ath is not None and ath > 0:
            for kind, level in (("correction", _num(rec.get("px_correction"))),
                                ("bear", _num(rec.get("px_bear")))):
                if level is None or not (prev > level >= price):
                    continue
                found.append((kind, round(level, 2), "down", {
                    "threshold_px": round(level, 2),
                    "pct_from_ath_live": round((price - ath) / ath * 100.0, 2),
                    "ath": round(ath, 2),
                    "ath_date": ath_date,
                }))
            if prev < ath <= price:
                found.append(("ath", round(ath, 2), "up", {
                    "threshold_px": round(ath, 2),
                    "pct_from_ath_live": round((price - ath) / ath * 100.0, 2),
                    "ath": round(ath, 2),
                    "ath_date": ath_date,
                }))

        if price >= min_price:
            levels = {_num(rec.get("round_above")), _num(rec.get("round_below"))}
            for level in sorted(x for x in levels if x is not None):
                up = prev < level <= price
                down = prev > level >= price
                if not (up or down):
                    continue
                found.append(("round", round(level, 2), "up" if up else "down", {
                    "level": round(level, 2),
                }))

        shares = _num(rec.get("shares_est"))
        if shares is not None and shares > 0:
            live_mc, prev_mc = shares * price, shares * prev
            for milestone in MCAP_MILESTONES:
                up = prev_mc < milestone <= live_mc
                down = prev_mc > milestone >= live_mc
                if not (up or down):
                    continue
                found.append(("mcap", int(milestone), "up" if up else "down", {
                    "milestone_usd": int(milestone),
                    "mcap_live_usd": round(live_mc),
                }))

        for kind, level, direction, extra in found:
            key = f"threshold:{sym}:{kind}:{level}:{day}"
            if key in fired:
                continue
            # A ROUND NUMBER IS NOT AN EVENT THE WAY A RECORD IS (reviewer M2).
            # Correction / bear / new-ATH / mcap crossings are tape; "$LLY
            # cleared $1,200" is arithmetic about a price that moves through a
            # multiple of 50 several times a year. At base 70 a mega-cap round
            # cross scored 90 and OUTRANKED a real rout for the flagship mirror;
            # base 60 caps the same event at 80, under the 85 flagship floor,
            # while it still ships on the wire desk.
            severity = 60.0 if kind == "round" else 70.0
            if rec.get("sp500"):
                severity += 10.0
            mcap = _num(rec.get("mcap_usd"))
            if mcap is not None and mcap >= 5e11:
                severity += 10.0
            severity = _clamp(severity)

            # WHEN DID THIS ACTUALLY CROSS? (2026-07-31 defect, see the
            # DEFAULTS note.) The test above is `prev_close` vs the live price,
            # which is true for the rest of the session once the level goes —
            # so on its own it can only support "trades below 325", never
            # "just broke below 325". The prior tick's memory is the only
            # evidence that upgrades it, and only when that memory is
            # trustworthy for THIS crossing: complete, recent, and at or above
            # its own severity floor. Everything else is UNKNOWN, and unknown
            # keeps the standing phrasing.
            cross_id = _cross_id(sym, kind, level)
            if prior is None or severity < float(prior.get("min_sev") or 0.0):
                basis = CROSS_UNKNOWN
            elif cross_id in prior["ids"]:
                basis = CROSS_EARLIER
            else:
                basis = CROSS_FIRST_SEEN

            facts: dict[str, Any] = {
                "ticker": sym,
                "kind": kind,
                "price": round(price, 2),
                "prev_close": round(prev, 2),
                "pct": round((price - prev) / prev * 100.0, 2) if prev else None,
                "direction": direction,
                "sector": rec.get("sector") or None,
                "cross_id": cross_id,
                "cross_basis": basis,
                # The one leaf the copy layer reads. A bool, so the numeric
                # gate cannot license a figure off it (_f/_walk_packet both
                # drop bools) and the LLM desk sees a flag, not a number.
                "crossed_in_window": basis == CROSS_FIRST_SEEN,
                "prior_tick_at": (prior or {}).get("at") or None,
            }
            facts.update(extra)
            out.append(FactPacket(
                trigger="threshold_cross",
                key=key,
                fired_at=_iso(now),
                session=session_phase(now),
                ticker=sym,
                name=names.get(sym) or None,
                sector=rec.get("sector") or None,
                direction=direction,
                severity=severity,
                facts=facts,
                provenance=_provenance(pack, quotes_asof, quote, bridged, demo),
            ))
    return out


def _detect_streaks(
    quotes: dict,
    pack: dict | None,
    heatmap: dict | None,
    fired: set[str],
    now: datetime,
    cfg: dict,
    demo: bool,
    bridged: bool,
    quotes_asof: Any,
) -> list[FactPacket]:
    """streak_rarity: today extends a run the pack says is multi-year rare (§2 T3)."""
    out: list[FactPacket] = []
    if not bridged:
        return out
    min_len = int(_c(cfg, "detectors.streak.min_len", 5))
    min_rarity = float(_c(cfg, "detectors.streak.min_rarity_days", 365))
    day = _day(now)
    today = _utc(now).date()
    names = {
        str(t.get("t") or "").upper(): str(t.get("name") or "")
        for t in ((heatmap or {}).get("tiles") or []) if isinstance(t, dict)
    }

    for sym, rec in sorted(((pack or {}).get("tickers") or {}).items()):
        sym = str(sym).upper()
        if not isinstance(rec, dict) or not _history_ok(rec, pack, bridged):
            # Per-record gate as well as the global one: a run counted off a
            # record that stopped updating six sessions ago is not a streak,
            # it is a fossil.
            continue
        quote = quotes.get(sym)
        if not isinstance(quote, dict):
            continue
        pct = _num(quote.get("change_pct"))
        if pct is None or pct == 0:
            continue
        streak = rec.get("streak") if isinstance(rec.get("streak"), dict) else {}
        s_dir, s_len = streak.get("dir"), _num(streak.get("len"))
        if s_len is None or s_dir not in ("up", "down"):
            continue
        direction = "up" if pct > 0 else "down"
        if direction != s_dir:
            continue
        len_today = int(s_len) + 1
        if len_today < min_len:
            continue
        since = (streak.get("last_run_ge") or {}).get(str(len_today))
        since_date = _parse_iso_date(since)
        if since_date is not None and (today - since_date).days < min_rarity:
            continue
        key = f"streak:{sym}:{day}"
        if key in fired:
            continue
        out.append(FactPacket(
            trigger="streak_rarity",
            key=key,
            fired_at=_iso(now),
            session=session_phase(now),
            ticker=sym,
            name=names.get(sym) or None,
            sector=rec.get("sector") or None,
            direction=direction,
            severity=_clamp(65.0 + _attention_boost(rec)),
            facts={
                "ticker": sym,
                "dir": direction,
                "len_today": len_today,
                "since": since,
                "window_start": rec.get("window_start"),
                "pct_today": round(pct, 2),
                "price": _r2(quote.get("price")),
            },
            provenance=_provenance(pack, quotes_asof, quote, bridged, demo),
        ))
    return out


def _detect_signals(
    quotes: dict,
    pack: dict | None,
    heatmap: dict | None,
    plan_signals: list[dict],
    fired: set[str],
    now: datetime,
    cfg: dict,
    demo: bool,
    bridged: bool,
    quotes_asof: Any,
) -> list[FactPacket]:
    """signal_fired: live price crosses a Prophet plan level (§3, proprietary event)."""
    out: list[FactPacket] = []
    today = _utc(now).date()
    names = {
        str(t.get("t") or "").upper(): str(t.get("name") or "")
        for t in ((heatmap or {}).get("tiles") or []) if isinstance(t, dict)
    }

    for sig in (plan_signals or []):
        if not isinstance(sig, dict):
            continue
        sym = str(sig.get("ticker") or "").upper()
        entry = _num(sig.get("entry"))
        signal_id = str(sig.get("signal_id") or "").strip()
        if not sym or entry is None or not signal_id:
            continue
        as_of = _parse_iso_date(sig.get("as_of"))
        if as_of is None or (today - as_of).days > 2:
            continue
        # DELIBERATELY UNDATED (unlike every other key here). load_fired is
        # day-scoped, so this key only suppresses re-fires WITHIN one day: a
        # level that is crossed again on a later day while the plan is still
        # armed is a fresh crossing and may post again. That is the intended
        # cross-day behaviour, not an omission — a plan level reclaimed two
        # sessions later is news; the same level ping-ponging at 10:05 and
        # 10:10 is not.
        key = f"signal:{signal_id}"
        if key in fired:
            continue
        quote = quotes.get(sym)
        if not isinstance(quote, dict):
            continue
        price, prev = _num(quote.get("price")), _num(quote.get("prev_close"))
        if price is None or prev is None:
            continue
        raw = str(sig.get("direction") or "").strip().lower()
        bear = raw in ("bear", "short", "down", "sell")
        if bear:
            if not (prev > entry >= price):
                continue
            direction = "down"
        else:
            if not (prev < entry <= price):
                continue
            direction = "up"
        rec = _pack_rec(pack, sym)
        severity = 55.0 + (10.0 if rec.get("sp500") else 0.0)
        out.append(FactPacket(
            trigger="signal_fired",
            key=key,
            fired_at=_iso(now),
            session=session_phase(now),
            ticker=sym,
            name=names.get(sym) or None,
            sector=rec.get("sector") or None,
            direction=direction,
            severity=_clamp(severity),
            facts={
                "ticker": sym,
                "level": round(entry, 2),
                "price": round(price, 2),
                "prev_close": round(prev, 2),
                "pct": round((price - prev) / prev * 100.0, 2) if prev else None,
                "direction": direction,
                "plan_as_of": sig.get("as_of"),
                "signal_id": signal_id,
            },
            provenance=_provenance(pack, quotes_asof, quote, bridged, demo),
        ))
    return out


def _detect_contrarian(
    quotes: dict,
    pack: dict | None,
    heatmap: dict | None,
    fired: set[str],
    now: datetime,
    cfg: dict,
    demo: bool,
    bridged: bool,
    quotes_asof: Any,
) -> list[FactPacket]:
    """contrarian_breadth: index red, defensives green (§2 T9, the corpus flip)."""
    out: list[FactPacket] = []
    tiles = [t for t in ((heatmap or {}).get("tiles") or []) if isinstance(t, dict)]
    if not tiles:
        return out
    index_sym = str(_c(cfg, "detectors.contrarian.index_ticker", "SPY")).upper()
    index_pct = _num((quotes.get(index_sym) or {}).get("change_pct"))
    limit = float(
        _c(cfg, "demo.contrarian_index_pct", DEFAULTS["demo"]["contrarian_index_pct"]) if demo
        else _c(cfg, "detectors.contrarian.index_pct", -1.5)
    )
    if index_pct is None or index_pct > limit:
        return out
    min_green = int(_c(cfg, "detectors.contrarian.min_green", 5))
    defensives = [
        str(s) for s in _c(cfg, "detectors.contrarian.defensive_sectors",
                           DEFAULTS["detectors"]["contrarian"]["defensive_sectors"])
    ]

    sectors_green: list[str] = []
    green: list[list[Any]] = []
    # THE UNIVERSE THE COUNT MOVES AGAINST (2026-07-31). "31 names across
    # Utilities and Consumer Defensive are green" is a numerator with no
    # denominator — 31 of how many? — which is the exact defect the desk feeds
    # closed for their own breadth line (market_facts.DENOMINATOR LAW, and the
    # "18 groups on the move today" string it names). It is counted here, in
    # the FACT, because the copy layer cannot invent a number the packet does
    # not carry: this is every live-quoted member of the sectors that qualified,
    # green and red alike, so the reader can see how broad "green" actually is.
    n_universe = 0
    for sector in defensives:
        members = [(str(t.get("t") or "").upper(), _tile_pct(t, quotes))
                   for t in tiles if str(t.get("sector") or "") == sector]
        pcts = [(s, p) for s, p in members if s and p is not None]
        if not pcts:
            continue
        if statistics.median([p for _, p in pcts]) > 0:
            sectors_green.append(sector)
            n_universe += len(pcts)
            green.extend([s, round(p, 2)] for s, p in pcts if p > 0)
    if len(sectors_green) < 2 or len(green) < min_green:
        return out

    key = f"contrarian:{_day(now)}"
    if key in fired:
        return out
    green.sort(key=lambda kv: kv[1], reverse=True)
    out.append(FactPacket(
        trigger="contrarian_breadth",
        key=key,
        fired_at=_iso(now),
        session=session_phase(now),
        ticker=None,
        name=None,
        sector=None,
        direction="up",
        severity=_clamp(75.0),
        facts={
            "index_pct": round(index_pct, 2),
            "index_ticker": index_sym,
            "green": green[:8],
            "sectors_green": sectors_green,
            "n_green": len(green),
            "n_defensive_members": n_universe,
        },
        provenance=_provenance(pack, quotes_asof, None, bridged, demo),
    ))
    return out


def _normalize_earnings(earnings: dict | None) -> dict:
    """Accept {"asof": ..., "tickers": {...}} or a bare {SYM: row} map.

    Same tolerance :func:`quotes_fresh` applies to the live-quote view, for the
    same reason: the caller should not have to remember which shape it holds.
    """
    if not isinstance(earnings, dict):
        return {"asof": None, "tickers": {}}
    rows = earnings.get("tickers")
    if isinstance(rows, dict):
        return {"asof": earnings.get("asof"),
                "tickers": {str(k).upper(): v for k, v in rows.items()
                            if isinstance(v, dict)}}
    return {"asof": None,
            "tickers": {str(k).upper(): v for k, v in earnings.items()
                        if isinstance(v, dict)}}


def _suppress_mover_overlap(events: list[FactPacket]) -> list[FactPacket]:
    """One story, one post: an earnings gap outranks its own mover twin.

    A name that gapped on a report trips BOTH detectors on the same tape (the
    mover bar and the earnings bar are the same |>=4%|). The earnings packet is
    strictly the better story — it names the cause and carries the EPS device —
    so the mover packet for that ticker is dropped. Mirrors the industry/parent
    overlap rule in :func:`_detect_group_moves`.

    "AND CARRIES THE EPS DEVICE" IS A CONDITION, NOT A DESCRIPTION (M3). A BMO
    reporter is routinely not filed by 09:30, so `_fresh_surprise` returns None
    and the packet has no beat/miss to state. Since the wire now REQUIRES the
    eps line on this family, such a packet renders nothing — and suppressing its
    mover twin as well would delete the name from the tape entirely on the one
    morning it is most worth reading. Without the EPS numbers the earnings
    packet is not the better story; it is the same story with a calendar entry,
    so the mover survives and posts as what it is.
    """
    covered = {p.ticker for p in events
               if p.trigger == "earnings_reaction" and p.ticker
               and (p.facts or {}).get("eps")}
    if not covered:
        return events
    return [p for p in events
            if not (p.trigger.startswith("mover_") and p.ticker in covered)]


def detect_events(
    quotes: dict | None,
    *,
    pack: dict | None = None,
    heatmap: dict | None = None,
    plan_signals: list[dict] | None = None,
    earnings: dict | None = None,
    ring: list[dict] | None = None,
    fired_today: list[dict] | None = None,
    now: datetime | None = None,
    cfg: dict | None = None,
    demo: bool = False,
) -> list[FactPacket]:
    """All firing events, severity-descending. PURE: no I/O, no LLM, no clock.

    `quotes` is {SYM: {price, prev_close, change_pct, ts_ms, source}} — the
    live_verify merge — or the {"quotes": ..., "asof": ...} wrapper.
    `earnings` is the calendar view the RADAR read from
    data/earnings/earnings.parquet ({"asof", "tickers": {SYM: {next_date,
    next_time, eps_forecast, surprises}}}) — this module never opens a parquet.
    `ring` is this lane's intraday memory. The THRESHOLD detector reads it (a
    "just broke below 325" claim is licensed only by the prior tick not having
    that crossing — see :func:`_prior_cross_state`); the P2 "$X added in 3
    hours" claims (masterplan T6) are still to come. Passing no ring is safe
    and costs only phrasing: every crossing degrades to the standing form.
    """
    try:
        t = _utc(now)
        cfg = cfg if isinstance(cfg, dict) else DEFAULTS
        quotes_asof = None
        if isinstance(quotes, dict) and isinstance(quotes.get("quotes"), dict):
            quotes_asof = quotes.get("asof")
            quotes = quotes["quotes"]
        q: dict[str, dict] = {
            str(k).upper(): v for k, v in (quotes or {}).items() if isinstance(v, dict)
        }
        fired_rows = list(fired_today or [])
        fired = _fired_keys(fired_rows)
        bridged = bridge_ok(pack, t, cfg=cfg)
        earn = _normalize_earnings(earnings)

        events: list[FactPacket] = []
        common = (q, pack, heatmap)
        lanes = (
            ("group", lambda: _detect_group_moves(*common, fired, t, cfg, demo, bridged, quotes_asof)),
            ("earnings", lambda: _detect_earnings(*common, earn, fired_rows, t, cfg,
                                                  demo, bridged, quotes_asof)),
            ("mover", lambda: _detect_movers(*common, fired_rows, t, cfg, demo, bridged, quotes_asof)),
            ("threshold", lambda: _detect_thresholds(*common, fired, t, cfg, demo, bridged,
                                                     quotes_asof, list(ring or []))),
            ("streak", lambda: _detect_streaks(*common, fired, t, cfg, demo, bridged, quotes_asof)),
            ("signal", lambda: _detect_signals(*common, list(plan_signals or []), fired, t,
                                               cfg, demo, bridged, quotes_asof)),
            ("contrarian", lambda: _detect_contrarian(*common, fired, t, cfg, demo, bridged, quotes_asof)),
        )
        for label, fn in lanes:
            try:
                events.extend(fn())
            except Exception as exc:  # noqa: BLE001
                log.warning("hot_tape: %s detector failed: %s", label, exc)
        events = _suppress_mover_overlap(events)
        # SEVERITY SATURATES, SO IT CANNOT BE THE ONLY KEY (reviewer M2). The
        # mover formula tops out at 100 well before the tape does: SNDK -14.25,
        # GLW -12.10 and AMD -8.15 all scored exactly 100 on the 2026-07-28
        # tape, and an alphabetical tie-break then handed the run cap to AMD and
        # dropped the biggest move of the day. Magnitude breaks the tie; the key
        # stays last so the order is still deterministic.
        events.sort(key=lambda p: (-float(p.severity), -abs(_magnitude(p) or 0.0), p.key))
        return events
    except Exception as exc:  # noqa: BLE001
        log.warning("hot_tape.detect_events failed: %s", exc)
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Two-step publish — the context brief (codex case study, 2026-07-28)
# ─────────────────────────────────────────────────────────────────────────────

#: The prefix :func:`brief_key` stamps. Named once so its inverse below cannot
#: drift away from it.
_BRIEF_KEY_PREFIX = "brief:"


def brief_key(alert_key: Any) -> str:
    """The fired-ledger key of the brief that follows `alert_key`.

    One brief per alert, forever: the row lands in the SAME append-only fired
    ledger the cooldowns use, so a later pass sees it and never files a second.
    """
    return f"{_BRIEF_KEY_PREFIX}{alert_key}"


def parent_alert_key(key: Any) -> str | None:
    """The alert key a brief is context FOR, or None when `key` is not a brief.

    The inverse of :func:`brief_key`. A consumer holding nothing but a brief's
    fired-ledger row needs this to find the alert and re-check that it is still
    posted: the "alert must have posted" gate is evaluated once, when the brief
    is BUILT, and a brief can sit queued for a while after that.
    """
    s = str(key or "")
    if not s.startswith(_BRIEF_KEY_PREFIX):
        return None
    return s[len(_BRIEF_KEY_PREFIX):] or None


def orphaned_brief_status(
    key: Any,
    trigger: Any,
    alert_item_by_key: dict[str, str],
    statuses: dict[str, str],
) -> str | None:
    """The parent's not-posted status when (key, trigger) name an orphaned
    context brief; None when this is not a brief or its alert is "posted".

    THE one predicate for "is this brief orphaned". Two call sites, one truth:
    the radar's dispatch re-check (scripts/hot_tape_radar.py dispatch_ids) and
    the publisher's send-time gate (scripts/marketing_publisher.py) both call
    this, so the two halves of the recall cascade cannot drift apart. A brief
    is recognised by EITHER its trigger or its brief-shaped key: a row that
    claims one but not the other is malformed, and a malformed brief must fail
    CLOSED (checked, and unresolvable) rather than ride out as an alert.

    Returns:
      * None           - not a context brief, or the parent alert is "posted"
      * a status string - the parent's folded status ("recalled", "quarantined", ...)
      * "unresolved"   - no parent can be named from `alert_item_by_key`/`statuses`

    What the caller does with a not-None answer is the caller's policy: the
    radar only DESTROYS on a resolved status (its same-day fired map is lossy,
    so "unresolved" is merely withheld), while the publisher quarantines on
    both (its map is built from the outbox ledger itself, the authority on
    statuses, so a parent it cannot name is positive evidence).
    """
    is_brief = str(trigger or "") == BRIEF_TRIGGER
    parent_key = parent_alert_key(key)
    if not is_brief and parent_key is None:
        return None
    parent_id = str(alert_item_by_key.get(parent_key) or "") if parent_key else ""
    status = statuses.get(parent_id) if parent_id else None
    if status == "posted":
        return None
    return str(status or "unresolved")


def _group_members(tiles: list[dict], kind: str, label: str) -> list[dict]:
    return [t for t in tiles if str(t.get(kind) or "").strip() == label]


def build_brief_packet(
    alert: dict,
    *,
    quotes: dict | None = None,
    pack: dict | None = None,
    heatmap: dict | None = None,
    now: datetime | None = None,
    cfg: dict | None = None,
    demo: bool = False,
    quotes_asof: Any = None,
) -> FactPacket | None:
    """The follow-up context packet for one already-posted alert, or None.

    `alert` is the alert's FIRED-LEDGER ROW (key / trigger / ticker / sector /
    direction / severity), not its FactPacket: the row is what the radar has in
    hand on the next tick, and everything the brief claims is recomputed from
    THIS pass's tape anyway. PURE — no I/O, no LLM, no clock.

    The mechanism is the whole point (codex: "a mechanism makes context worth
    reposting"), and it is engine-computed, never asserted: we compare the
    subject against its own peer group on the live tape and say which of two
    true things this is —

      * **group** — the peers moved with it, so this is a sector story;
      * **single_name** — the peers did not, so this is one name.

    Returns None when that comparison cannot be made honestly: no live quote, no
    identifiable group, or fewer than ``two_step.min_peers`` live peers. A brief
    with no mechanism is the "why it matters" sentence we have no receipt for,
    and gate 0.2's refusal applies to it exactly as it does to an alert.
    """
    try:
        t = _utc(now)
        if isinstance(quotes, dict) and isinstance(quotes.get("quotes"), dict):
            quotes_asof = quotes_asof if quotes_asof is not None else quotes.get("asof")
            quotes = quotes["quotes"]
        q: dict[str, dict] = {
            str(k).upper(): v for k, v in (quotes or {}).items() if isinstance(v, dict)
        }
        tiles = [x for x in ((heatmap or {}).get("tiles") or []) if isinstance(x, dict)]
        min_peers = int(_c(cfg, "two_step.min_peers", DEFAULTS["two_step"]["min_peers"]))
        group_min = float(_c(cfg, "two_step.group_median_pct",
                             DEFAULTS["two_step"]["group_median_pct"]))

        alert_key = str(alert.get("key") or "")
        alert_trigger = str(alert.get("trigger") or "")
        direction = str(alert.get("direction") or "")
        if not alert_key or direction not in ("up", "down"):
            return None
        sym = str(alert.get("ticker") or "").strip().upper() or None

        # ── Which group are we talking about, and who is in it? ──────────────
        if sym:
            tile = next((x for x in tiles
                         if str(x.get("t") or "").upper() == sym), None)
            if tile and str(tile.get("industry") or "").strip():
                group_kind, group = "industry", str(tile["industry"]).strip()
            elif tile and str(tile.get("sector") or "").strip():
                group_kind, group = "sector", str(tile["sector"]).strip()
            elif str(alert.get("sector") or "").strip():
                group_kind, group = "sector", str(alert["sector"]).strip()
            else:
                return None
        else:
            group = str(alert.get("sector") or "").strip()
            if not group:
                return None
            group_kind = ("industry"
                          if _group_members(tiles, "industry", group)
                          else "sector")

        members = _group_members(tiles, group_kind, group)
        peers: list[tuple[str, float]] = []
        for tile in members:
            psym = str(tile.get("t") or "").upper()
            pct = _tile_pct(tile, q)
            if psym and psym != sym and pct is not None:
                peers.append((psym, pct))
        if len(peers) < min_peers:
            return None

        peer_pcts = [p for _, p in peers]
        peer_median = statistics.median(peer_pcts)
        n_agree = len([p for p in peer_pcts
                       if (p < 0 if direction == "down" else p > 0)])
        with_it = ((peer_median < 0) if direction == "down" else (peer_median > 0))
        kind = ("group" if (with_it and abs(peer_median) >= group_min)
                else "single_name")

        ordered = sorted(peers, key=lambda kv: kv[1], reverse=(direction == "up"))
        top = [[s, round(p, 2)] for s, p in ordered[:3]]

        # ── The subject's own live read ─────────────────────────────────────
        pct = price = None
        quote = q.get(sym) if sym else None
        if sym:
            if not isinstance(quote, dict):
                return None
            pct = _num(quote.get("change_pct"))
            price = _num(quote.get("price"))
            if pct is None:
                return None

        facts: dict[str, Any] = {
            "subject": sym or group,
            # Only a GROUP brief leads with a label; a single-name brief leads
            # with its cashtag, and the label slot staying None is what keeps
            # the two template shapes from renting each other's copy.
            "subject_label": None if sym else group,
            "ticker": sym,
            "sector": group,
            "alert_key": alert_key,
            "alert_trigger": alert_trigger,
            "pct": round(pct, 2) if pct is not None else None,
            "price": _r2(price),
            "mechanism": {
                "kind": kind,
                "group": group,
                "group_kind": group_kind,
                "peer_median_pct": round(peer_median, 2),
                "n_peers": len(peers),
                "n_agree": n_agree,
            },
            "peers": top,
            "watch": ({"kind": "level", "price": _r2(price)} if sym and price is not None
                      else {"kind": "breadth", "n_agree": n_agree,
                            "n_members": len(peers)}),
        }
        return FactPacket(
            trigger=BRIEF_TRIGGER,
            key=brief_key(alert_key),
            fired_at=_iso(t),
            session=session_phase(t),
            ticker=sym,
            name=None,
            sector=group,
            direction=direction,
            severity=_clamp(_num(alert.get("severity")) or 0.0),
            facts=facts,
            provenance=_provenance(pack, quotes_asof, quote, bridge_ok(pack, t, cfg=cfg),
                                   demo),
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("hot_tape.build_brief_packet failed: %s", exc)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Routing + outbox handoff
# ─────────────────────────────────────────────────────────────────────────────

def severity_account(packet: FactPacket, cfg: dict | None = None) -> str:
    """Wire desk by default; flagship mirrors only the biggest events.

    PURE ROUTING — it answers "which desk OWNS this event", never "is that desk
    armed". Liveness is :func:`live_account`, deliberately a separate call for
    the reason wire_routing states in capitals: LIVENESS IS NOT ROUTING. An
    emitter that consulted desk_network here would silently rewrite the routing
    table every time an operator flipped a switch, and the config would stop
    describing the system.
    """
    try:
        floor = float(_c(cfg, "emit.flagship_severity_floor", 85))
        if float(packet.severity) >= floor:
            return str(_c(cfg, "emit.flagship_account", "flagship"))
        return str(_c(cfg, "emit.account", "mastermind_news"))
    except Exception as exc:  # noqa: BLE001
        log.warning("hot_tape.severity_account failed: %s", exc)
        return str(_c(cfg, "emit.account", "mastermind_news"))


#: Accounts this process has already announced as dark. The radar ticks every
#: five minutes and books up to three items a pass, so an unarmed target would
#: otherwise print the same annotation hundreds of times a day and bury the
#: Actions summary it exists to fill. Keyed by account, not by (event, account):
#: the operator's action is the same one desk_network flip either way.
_WARNED_DARK_ACCOUNTS: set[str] = set()


def reset_dark_account_warnings() -> None:
    """Clear the once-per-process dark-account warning set (tests)."""
    _WARNED_DARK_ACCOUNTS.clear()


def live_account(
    candidate: str,
    *,
    marketing_cfg: dict | None,
    root: Any = None,
    fallbacks: tuple[str, ...] = (),
) -> str:
    """``candidate`` if desk_network has it armed, else the first armed fallback.

    THE GRAVE THIS CLOSES. ``emit.account`` defaults to ``mastermind_news``,
    and :func:`severity_account` routes every sub-85 event there — i.e. most of
    the lane's volume. While that desk was dark, each of those items was
    rendered (a Chrome raster), phrased (an LLM call), uploaded to R2, and
    enqueued — and then quarantined at dispatch with reason ``account_disabled``.
    The whole pipeline ran, paid, and posted nothing. Measured from
    ``outbox.fold_state`` on 2026-08-02: **29** such quarantines, every one of
    them ``mastermind_news`` on the ``hot_tape`` lane, 11 on 07-30 and 18 on
    07-31 — against 5 hot-tape items that posted in the same window, all 5 to
    ``flagship``. ``wire_routing`` was built precisely to stop this, and the
    hot-tape lane never called it.

    ``mastermind_news`` ARMED 2026-08-02 (masterplan §8.2 W4f), so on today's
    config this function is a no-op for that desk. That is not a reason to
    remove it and it is not a reason to weaken its test: the rescue is a
    property of the LANE (any target, any day), not a patch for one account's
    switch position, and the switch can go back. Its guard therefore pins the
    BEHAVIOUR against a config whose target is dark rather than pinning the
    account by name — see tests/test_marketing_wire_headroom.py.

    Resolution uses ``wire_routing._enabled_accounts`` — the SAME liveness read
    the press wire uses, deliberately not a second implementation, because two
    answers to "is this desk armed" is how a routing table starts lying. It is
    private by name only; the alternative is a duplicate accounts-model read in
    this file, and the brief that ordered this fix named it as the seam.

    THREE ANSWERS, NOT TWO. ``_enabled_accounts`` returns None when the accounts
    model could not be consulted, and an empty set when the config carries no
    ``desk_network`` roster at all. NEITHER is evidence that ``candidate`` is
    dark, so both keep the candidate untouched and print nothing. Rerouting a
    correctly-configured desk's volume on the strength of an import failure or a
    config-less checkout (every unit-test fixture is one) would be a silent,
    invisible redirection — a worse fault than the one being fixed.

    THE CONFIG OVERRIDE KEEPS WORKING: an operator who points ``emit.account`` at
    an ENABLED desk gets that desk, unconditionally and silently. This function
    only ever moves an item off a target the accounts model says is off.
    """
    acct = str(candidate or "").strip()
    if not acct:
        return acct
    try:
        from engine.marketing import wire_routing as _wr  # noqa: PLC0415

        live = _wr._enabled_accounts(marketing_cfg, root)
        if not live:
            # None (unknown) or empty (no roster) — see the docstring. Not proof.
            return acct
        if acct in live:
            return acct
        # Ladder: the caller's own preferences first (flagship mirror desk, wire
        # desk), then wire_routing's configured default, then any armed desk —
        # sorted so the choice is deterministic across runs rather than
        # dict-order roulette.
        ladder = [str(f or "").strip() for f in fallbacks]
        ladder.append(_wr.default_account(marketing_cfg))
        ladder.extend(sorted(live))
        target = next((f for f in ladder if f and f in live), "")
        if not target:
            return acct
        if acct not in _WARNED_DARK_ACCOUNTS:
            _WARNED_DARK_ACCOUNTS.add(acct)
            # Start-of-line bare print (house law): routed through a logger this
            # annotation is prefixed and GitHub drops it silently — and a lane
            # quietly posting as a different desk than its config names is
            # exactly what must not be silent.
            print(
                f"::warning title=hot-tape-dark-account::hot-tape routes to "
                f"{acct!r}, which is not enabled in desk_network — posting as "
                f"{target!r} instead so the item is not enqueued to a grave "
                f"(items addressed to a dark desk quarantine at dispatch with "
                f"reason account_disabled). Arm the desk in desk_network, or "
                f"point hot_tape emit.account at a live one.",
                flush=True,
            )
        return target
    except Exception as exc:  # noqa: BLE001 — routing must never break a pass
        log.warning("hot_tape.live_account failed (%s) — keeping %r", exc, acct)
        return acct


def packet_to_source(packet: FactPacket, media: dict | None = None) -> dict:
    """The outbox item's `source` dict: provenance the publisher can gate on.

    `baseline_pct` is the headline move the copy claims, carried for PROVENANCE
    and PARITY with the rest of the outbox (and so a future gate extension has
    the number already in hand). Be precise about what it does NOT buy today:
    the post-time tape gate does not evaluate ``kind="breaking"`` items at all,
    so nothing re-checks this figure against the live quote before sending. The
    protection that IS live for this lane is upstream — the freshness gate, the
    bridge/per-record history gates, and the numeric-consistency gate in
    hot_tape_wire — plus the operator kill switch, and downstream the publisher's
    dispatch-time dark-desk park (an item addressed to a desk that is not
    enabled in desk_network quarantines at dispatch, reason account_disabled,
    post_now included — severity_account routes by severity alone and never
    consults liveness).
    """
    try:
        prov = packet.provenance or {}
        source: dict[str, Any] = {
            "lane": LANE,
            "trigger": packet.trigger,
            "ticker": packet.ticker,
            "sector": packet.sector,
            "direction": packet.direction,
            "severity": packet.severity,
            "baseline_pct": _magnitude(packet),
            "quote_ts_ms": prov.get("quote_ts_ms"),
            "quote_source": prov.get("quote_source"),
            "pack_asof": prov.get("pack_asof"),
            "bridge_ok": bool(prov.get("bridge_ok")),
            "demo": bool(prov.get("demo")),
            "fact_packet": asdict(packet),
        }
        for k in ("media_url", "media_png_path", "chart_id"):
            if isinstance(media, dict) and media.get(k) is not None:
                source[k] = media[k]
        return source
    except Exception as exc:  # noqa: BLE001
        log.warning("hot_tape.packet_to_source failed: %s", exc)
        return {"lane": LANE, "trigger": getattr(packet, "trigger", None)}
