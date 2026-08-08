"""Group earnings pulse — Wave GR2 of the Group Reads program
(research/GROUP_READS_MASTERPLAN_BY_FABLE.md).

AUTHORITY
=========
    schema:    group_earnings_pulse.v1
    authority: context_only

DISPLAY / CONTEXT TIER ONLY. Nothing in this module ranks, sizes, gates, alerts, or
grants entry authority, and it never fuses its legs into a cross-basket score. It is
the earnings LAYER of a basket read: where the group is in its reporting cycle, how the
prints landed, which way management is talking, whether the analyst wave is broadening,
what happened in the five sessions after the print, and — the leg nothing else here has —
whether the basket's members actually MOVE TOGETHER around each other's earnings.

Every stat carries its own n. Every floor refusal prints a null rather than a
survivor-only number. A member with no data lands in `n_no_data`; it never silently
shrinks a denominator (resolution-conditioned-denominator law). A missing input store
degrades to disclosed nulls — it never fabricates and never raises into the nightly.
An LLM consumer may de-escalate these reads; it may never originate one.

THE ARTIFACT
============
`site/basketdata/earnings_pulse.json` — a dict keyed by basket_id, one
`group_earnings_pulse.v1` object per US basket in data/baskets/membership.json, built
from the members that are LIVE as of the run date (`added` <= as_of, `removed` unset or
> as_of). The key set of every block is CONSTANT: a refused stat is null next to its
own n, never an absent key. Unknown keys are contract violations
(tests/test_group_earnings_contract.py).

INPUTS (all committed artifacts — this module opens no network at build time)
============================================================================
    data/earnings/earnings.parquet        collectors/equity_earnings.py — ticker-indexed
                                          next_date / next_time / eps_forecast /
                                          surprises_json (last 4 quarters: qtr, reported,
                                          eps, consensus, surprise_pct)
    data/edgar/earnings_8k_dates.parquet  collectors/edgar_earnings_8k.py — the deep
                                          Item-2.02 announcement history (ticker,
                                          filing_date, acceptance_datetime, items) that
                                          the 8-quarter sympathy window needs; the Nasdaq
                                          store only reaches back four quarters
    data/edgar/guidance_hits.parquet      via engine.guidance_gap (imported, not forked)
    data/revisions/latest.parquet         collectors/equity_revisions.py, the same store
                                          engine.theme_revisions rolls up
    data/baskets/ohlcv/<T>.parquet        member closes (`close`, Date index)
    yahoo/SPY (lib.store)                 the benchmark close cache engine.baskets and
                                          engine.group_flow already benchmark against —
                                          `store.read("yahoo", "SPY")["close"]`

DISCLOSED RULES (deterministic and stated is what matters; each is pinned by a test)
====================================================================================
REACTION SESSION. An announcement is mapped to the session that first prices it. The
    8-K store's `acceptance_datetime` is UTC, so: accepted BEFORE 14:30 UTC -> the first
    session at-or-after that UTC date (a pre-open print moves the stock that day);
    accepted at-or-after 14:30 UTC -> the first session STRICTLY AFTER it (an after-hours
    print moves the stock the next session). 14:30 UTC is 09:30 ET under EST and 10:30 ET
    under EDT, so the rule is exact for pre-open and after-hours prints in both halves of
    the year and errs only for the rare intraday 2.02 filing during a winter morning. No
    tz database is required, which keeps the rule identical on every runner. A Nasdaq
    `reported` date carries no time; it is treated as after-hours (the modal case) unless
    an 8-K event for the same ticker sits within REPORT_MATCH_SESSIONS sessions, in which
    case the timed 8-K event wins and the Nasdaq surprise is attached to it.

SEASON. A member counts as REPORTED when its most recent reaction session falls inside
    the trailing SEASON_LOOKBACK_SESSIONS (75) sessions ending at `as_of`. 75 sessions is
    ~105 calendar days: one full quarterly cycle plus the late-reporter tail, so in a
    normal cycle exactly one report per member falls inside it. Only the LATEST report is
    ever counted, so a member on a broken cycle can read 0 but never double-counts.
    `n_upcoming_14d` counts members whose `next_date` lands in (as_of, as_of + 14 days];
    `session` is amc/bmo only when the store supplies `next_time`, else "unknown".

RESULTS. Per member, the latest-quarter Nasdaq surprise whose reaction session is inside
    the season window: beat = surprise > 0, miss = surprise < 0, inline = exactly 0.
    `surprise_pct` is preferred; when it is absent the sign of (eps - consensus) is used.
    Floor MIN_REPORTED (4) classified members, else every count nulls and n_no_data
    absorbs the whole membership. n_beat + n_miss + n_inline + n_no_data == n_members,
    always.

GUIDANCE. engine.guidance_gap's classifier is IMPORTED, never re-implemented: the same
    `_theme_guidance` rollup runs over basket members instead of curated themes, so the
    latest-direction-per-ticker resolution, the RECENT_DAYS window, and the band ladder
    are shared code. Its >=MIN_FILERS (2) distinct-filers law is preserved exactly — below
    it, this artifact prints `band: null` rather than guidance_gap's NEUTRAL, because a
    null is the honest disclosure of "too thin to call" where NEUTRAL reads as a call.

REVISIONS. engine.theme_revisions' member-rollup pattern (its MIN_ANALYSTS coverage gate
    is imported so it cannot drift): `net_up_share` is the share of covered members whose
    net-up revision breadth is positive, `n_covered` the number of members clearing the
    coverage gate. Floor MIN_COVERED (4), else null.

DRIFT. Members whose season reaction session is at least DRIFT_SESSIONS (5) sessions
    before `as_of`: the share with a positive cumulative SPY-adjusted return from the
    REACTION session's close to five sessions later — post-announcement drift measured
    after the initial gap, not through it. Floor MIN_DRIFT_N (4), else null.

SYMPATHY. The signature leg: do earnings move this basket TOGETHER? Over the trailing
    WINDOW_Q (8) quarters of member reaction sessions, pool every |SPY-adjusted same-day
    move| of the members that were NOT reporting that day (co-reporters are excluded — on
    their own report day you would be measuring their reaction, not sympathy; an event
    needs MIN_COHORT (3) such members to count). `ratio` is the median of that pooled
    event-day set divided by the SAME members' unconditional baseline median |SPY-adjusted
    move| over every session in the window that is NOT a report day for ANY member of the
    basket. Floors n_events >= 12 AND n_reporters >= 4, else the whole block nulls with
    the counts still printed. The directional split reports the median SIGNED non-reporter
    move on beat days vs miss days (by the reporter's own surprise sign), each requiring
    MIN_DIRECTIONAL_DAYS (5) event days or that half nulls on its own.

COVERAGE, MEASURED (2026-08-08, the store as committed). The 8-K spine is deep — 13+ years
    of Item-2.02 dates for a mega-cap — but the CONSENSUS half is thin: the Nasdaq surprise
    history is a budgeted drip (~120 names/run, see collectors/equity_earnings.py's ROTATION
    CONTRACT), so only 715 of 1,976 stored names, and 201 of 653 live basket members, carry
    any surprise history at all. That is why 18 of 49 baskets refuse the results block on
    this snapshot. Those members are counted in `n_no_data`, never dropped — a beat share
    computed over only the dripped members would be a survivor statistic. edgar_eps
    (data/edgar/eps_quarterly.parquet) is deliberately NOT substituted: it carries actual
    EPS with NO consensus, so anything built from it would be a different statistic wearing
    the `eps_surprise vs consensus` label. The block recovers on its own as the drip fills.

HONEST LIMITS. Sympathy is a co-movement DESCRIPTION, not a causal claim and not a trade:
    a basket whose members report in the same week will read high partly because the sector
    tape moves for reasons unrelated to any one print, and the SPY adjustment removes market
    beta but not sector beta. Beat/miss is a Nasdaq/community consensus, not official
    guidance, and dates can move. Guidance is a coarse language band with no negation
    handling. None of these are graded signals; the gauntlet applies only if any of them is
    ever proposed for authority, and nothing here is.

LEDGER. data/group_pulse/sympathy.parquet — one immutable row per (basket_id, event_date,
    reporter_ticker), appended ONLY on the nightly lane (engine.ledger_lane). Rows are
    historical facts: a later run may add new event days, never rewrite an existing one.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from engine.ledger_lane import nightly_advance_enabled as _ledger_advance_enabled
from lib import config, store

log = logging.getLogger(__name__)

SCHEMA = "group_earnings_pulse.v1"
AUTHORITY = "context_only"

# --- season / calendar -------------------------------------------------------------
SEASON_LOOKBACK_SESSIONS = 75   # trailing sessions that define "this quarterly cycle"
UPCOMING_DAYS = 14              # calendar-day horizon for n_upcoming_14d
MAX_NEXT = 6                    # cap on the `season.next` preview list
#: An announcement date from the (untimed) Nasdaq store is folded into a timed 8-K event
#: when the two sit within this many sessions of each other.
REPORT_MATCH_SESSIONS = 3
#: UTC cut that separates a pre-open print (prices that session) from an after-hours one
#: (prices the next session). See DISCLOSED RULES above for why this is UTC, not ET.
PREOPEN_CUT_UTC_MINUTES = 14 * 60 + 30

# --- floors (a stat below its floor prints null, never a survivor-only number) -------
MIN_REPORTED = 4                # results block
MIN_COVERED = 4                 # revisions block
MIN_DRIFT_N = 4                 # drift block
MIN_SYMPATHY_EVENTS = 12        # sympathy ratio
MIN_SYMPATHY_REPORTERS = 4      # sympathy ratio
MIN_DIRECTIONAL_DAYS = 5        # each half of the directional split
MIN_COHORT = 3                  # non-reporting members needed for an event to count

# --- windows ------------------------------------------------------------------------
WINDOW_Q = 8                    # quarters of report days behind the sympathy stat
SESSIONS_PER_QUARTER = 63       # ~63 NYSE sessions in a quarter
DRIFT_SESSIONS = 5              # post-report drift horizon

BEAT_BASIS = "eps_surprise vs consensus; floor n_reported>=4"
BEAT_BASIS_REFUSED = ("eps_surprise vs consensus; floor n_reported>=4 not met — "
                      "counts withheld, every member reported as n_no_data")
GUIDANCE_BASIS = "guidance_gap generalized; >=2 distinct filers else null"
SYMPATHY_BASIS = (
    "median |SPY-adj same-day move| of non-reporting members on member report days "
    "÷ those members' unconditional baseline median |move| (baseline excludes every "
    "basket-member report day); floors: n_events>=12 AND n_reporters>=4, else null")


# ---------------------------------------------------------------------------
# Loaders — every one is fail-soft: a missing/unreadable store returns None and
# the leg that reads it degrades to a disclosed null.
# ---------------------------------------------------------------------------

def _membership() -> dict | None:
    """The basket registry (data/baskets/membership.json), via engine.baskets."""
    from engine.baskets import _membership as _m
    return _m()


def _earnings_store() -> pd.DataFrame | None:
    """collectors/equity_earnings.py's ticker-indexed calendar + surprise store."""
    p = config.data_dir() / "earnings" / "earnings.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("group_earnings: earnings store unreadable: %s", e)
        return None
    return df if (df is not None and not df.empty) else None


def _has_item_202(raw) -> bool:
    """Exact-token Item-2.02 test.

    Prefers collectors.edgar_earnings_8k.has_item_202 (the guard-tested definition), but
    that module imports `requests` at module scope, so the import is lazy and falls back
    to a byte-for-byte equivalent local check — split on commas, strip, membership of the
    exact token "2.02". NEVER substring matching, which would also swallow "12.02".
    tests/test_group_earnings_sympathy.py pins the two against each other."""
    try:
        from collectors.edgar_earnings_8k import has_item_202
        return bool(has_item_202(raw))
    except Exception:  # noqa: BLE001 — requests may be absent in a minimal test env
        if not raw or not isinstance(raw, str):
            return False
        return "2.02" in [t.strip() for t in raw.split(",") if t.strip()]


def _eightk_results() -> pd.DataFrame | None:
    """Item-2.02 announcement rows from data/edgar/earnings_8k_dates.parquet."""
    p = config.data_dir() / "edgar" / "earnings_8k_dates.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("group_earnings: earnings_8k_dates unreadable: %s", e)
        return None
    if df is None or df.empty or "ticker" not in df.columns or "filing_date" not in df.columns:
        return None
    if "items" in df.columns:
        df = df[df["items"].map(_has_item_202)]
    return df if not df.empty else None


def _revisions() -> pd.DataFrame | None:
    """collectors/equity_revisions.py's ticker-indexed latest snapshot."""
    p = config.data_dir() / "revisions" / "latest.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("group_earnings: revisions latest unreadable: %s", e)
        return None
    return df if (df is not None and not df.empty) else None


def _member_closes(tickers: list[str]) -> pd.DataFrame:
    """Close matrix over data/baskets/ohlcv — read ONCE for the whole sweep (members
    overlap heavily across baskets, so a per-basket read would be ~10x the IO)."""
    base = config.data_dir() / "baskets" / "ohlcv"
    cols: dict[str, pd.Series] = {}
    for t in tickers:
        p = base / f"{t}.parquet"
        if not p.exists():
            continue
        try:
            s = pd.read_parquet(p, columns=["close"])["close"]
        except Exception:  # noqa: BLE001 — one unreadable member never blocks the sweep
            continue
        s = s[~s.index.duplicated(keep="last")]
        cols[t] = pd.to_numeric(s, errors="coerce")
    if not cols:
        return pd.DataFrame()
    df = pd.DataFrame(cols)
    df.index = pd.DatetimeIndex(df.index).as_unit("ms")
    return df.sort_index()


def _spy_close(idx: pd.DatetimeIndex) -> pd.Series | None:
    """SPY closes on the member session grid — the same benchmark cache engine.baskets
    and engine.group_flow read (`store.read("yahoo", "SPY")`)."""
    try:
        df = store.read("yahoo", "SPY")
    except Exception as e:  # noqa: BLE001
        log.warning("group_earnings: SPY store unreadable: %s", e)
        return None
    if df is None or "close" not in getattr(df, "columns", []):
        return None
    s = pd.to_numeric(df["close"], errors="coerce").dropna()
    if s.empty:
        return None
    s.index = pd.DatetimeIndex(s.index).as_unit("ms")
    return s[~s.index.duplicated(keep="last")].sort_index().reindex(idx).ffill()


# ---------------------------------------------------------------------------
# Membership
# ---------------------------------------------------------------------------

def _live_members(basket: dict, as_of: pd.Timestamp) -> list[str]:
    """Members live as of the run date: `added` <= as_of and (`removed` unset or > as_of).
    Mirrors engine.baskets._ew_level's [added, removed) mask so this artifact and the
    basket level always describe the same roster."""
    out: list[str] = []
    for m in basket.get("members") or []:
        t = m.get("ticker")
        if not t:
            continue
        try:
            added = pd.Timestamp(m.get("added"))
        except Exception:  # noqa: BLE001
            continue
        if pd.isna(added) or added > as_of:
            continue
        rem = m.get("removed")
        if rem:
            try:
                if pd.Timestamp(rem) <= as_of:
                    continue
            except Exception:  # noqa: BLE001
                pass
        out.append(str(t))
    return sorted(dict.fromkeys(out))


# ---------------------------------------------------------------------------
# Report events — the (ticker -> reaction sessions) map every leg reads
# ---------------------------------------------------------------------------

def _session_at_or_after(sessions: pd.DatetimeIndex, day: pd.Timestamp) -> pd.Timestamp | None:
    i = int(sessions.searchsorted(day, side="left"))
    return sessions[i] if i < len(sessions) else None


def _session_after(sessions: pd.DatetimeIndex, day: pd.Timestamp) -> pd.Timestamp | None:
    i = int(sessions.searchsorted(day, side="right"))
    return sessions[i] if i < len(sessions) else None


def _reaction_session(sessions: pd.DatetimeIndex, day: pd.Timestamp,
                      minutes_utc: float | None) -> pd.Timestamp | None:
    """Map an announcement to the session that first prices it (see DISCLOSED RULES).

    `minutes_utc` is minutes-past-midnight UTC of the acceptance stamp, or None when the
    source carries no time — an untimed announcement is treated as after-hours, the modal
    case for an earnings release."""
    if minutes_utc is not None and minutes_utc < PREOPEN_CUT_UTC_MINUTES:
        return _session_at_or_after(sessions, day)
    return _session_after(sessions, day)


def _parse_surprises(raw) -> list[dict]:
    """Nasdaq surprises_json -> [{"reported": Timestamp, "surprise_pct": float|None}]."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:  # noqa: BLE001
            return []
    if not isinstance(raw, (list, tuple, np.ndarray)):
        return []
    out: list[dict] = []
    for e in raw:
        if not isinstance(e, dict):
            continue
        d = pd.to_datetime(e.get("reported"), errors="coerce", format="mixed")
        if pd.isna(d):
            continue
        sp = e.get("surprise_pct")
        try:
            sp = None if sp is None or pd.isna(sp) else float(sp)
        except (TypeError, ValueError):
            sp = None
        if sp is None:                       # fall back to the raw actual-vs-consensus gap
            try:
                eps, cons = float(e.get("eps")), float(e.get("consensus"))
                sp = eps - cons
            except (TypeError, ValueError):
                sp = None
        out.append({"reported": pd.Timestamp(d).normalize().as_unit("ms"),
                    "surprise_pct": sp})
    return sorted(out, key=lambda r: r["reported"])


def build_report_events(tickers: list[str], sessions: pd.DatetimeIndex,
                        earn: pd.DataFrame | None,
                        eightk: pd.DataFrame | None) -> dict[str, list[dict]]:
    """{ticker: [{"event_date", "announced", "source", "surprise_pct"}, ...]} sorted by
    event_date, one entry per distinct reaction session.

    The 8-K Item-2.02 history is the SPINE (it reaches back years and carries acceptance
    times); the Nasdaq store contributes the surprise magnitude and covers names EDGAR's
    8-K sweep has not reached. A Nasdaq date within REPORT_MATCH_SESSIONS sessions of an
    8-K event is folded INTO that event rather than counted twice."""
    want = set(tickers)
    events: dict[str, dict[pd.Timestamp, dict]] = {t: {} for t in want}
    if len(sessions) == 0:
        return {t: [] for t in want}

    if eightk is not None and not eightk.empty:
        e = eightk[eightk["ticker"].astype(str).isin(want)].copy()
        if not e.empty:
            fd = pd.to_datetime(e["filing_date"], errors="coerce", utc=False)
            acc = (pd.to_datetime(e["acceptance_datetime"], errors="coerce", utc=True)
                   if "acceptance_datetime" in e.columns else pd.Series(pd.NaT, index=e.index))
            for tkr, f, a in zip(e["ticker"].astype(str), fd, acc):
                if pd.isna(f):
                    continue
                if pd.notna(a):
                    day = pd.Timestamp(a.date()).as_unit("ms")
                    minutes = float(a.hour) * 60.0 + float(a.minute)
                else:
                    day, minutes = pd.Timestamp(f).normalize().as_unit("ms"), None
                sess = _reaction_session(sessions, day, minutes)
                if sess is None:
                    continue
                events[tkr].setdefault(sess, {
                    "event_date": sess, "announced": day, "source": "8k",
                    "surprise_pct": None})

    if earn is not None and not earn.empty and "surprises_json" in earn.columns:
        for tkr in want:
            if tkr not in earn.index:
                continue
            row = earn.loc[tkr]
            if isinstance(row, pd.DataFrame):
                row = row.iloc[-1]
            for rec in _parse_surprises(row.get("surprises_json")):
                sess = _reaction_session(sessions, rec["reported"], None)
                if sess is None:
                    continue
                near = _nearest_event(events[tkr], sess, sessions)
                if near is not None:
                    if events[tkr][near]["surprise_pct"] is None:
                        events[tkr][near]["surprise_pct"] = rec["surprise_pct"]
                    continue
                events[tkr][sess] = {"event_date": sess, "announced": rec["reported"],
                                     "source": "nasdaq", "surprise_pct": rec["surprise_pct"]}

    return {t: sorted(v.values(), key=lambda r: r["event_date"]) for t, v in events.items()}


def _nearest_event(existing: dict, sess: pd.Timestamp,
                   sessions: pd.DatetimeIndex) -> pd.Timestamp | None:
    """The already-recorded event within REPORT_MATCH_SESSIONS sessions of `sess`, if any."""
    if not existing:
        return None
    i = int(sessions.searchsorted(sess, side="left"))
    best, best_gap = None, None
    for k in existing:
        j = int(sessions.searchsorted(k, side="left"))
        gap = abs(i - j)
        if gap <= REPORT_MATCH_SESSIONS and (best_gap is None or gap < best_gap):
            best, best_gap = k, gap
    return best


# ---------------------------------------------------------------------------
# Blocks
# ---------------------------------------------------------------------------

_SESSION_MAP = {"time-after-hours": "amc", "time-pre-market": "bmo"}


def _season(members: list[str], events: dict[str, list[dict]],
            earn: pd.DataFrame | None, sessions: pd.DatetimeIndex,
            as_of: pd.Timestamp) -> tuple[dict, dict[str, dict]]:
    """Season clock + the latest in-season report per member (which results/drift read)."""
    floor_i = max(0, len(sessions) - SEASON_LOOKBACK_SESSIONS)
    season_start = sessions[floor_i] if len(sessions) else as_of

    latest: dict[str, dict] = {}
    for t in members:
        in_season = [e for e in events.get(t, [])
                     if season_start <= e["event_date"] <= as_of]
        if in_season:
            latest[t] = in_season[-1]

    upcoming: list[dict] = []
    horizon = as_of + pd.Timedelta(days=UPCOMING_DAYS)
    if earn is not None and not earn.empty and "next_date" in earn.columns:
        for t in members:
            if t not in earn.index:
                continue
            row = earn.loc[t]
            if isinstance(row, pd.DataFrame):
                row = row.iloc[-1]
            d = pd.to_datetime(row.get("next_date"), errors="coerce")
            if pd.isna(d):
                continue
            d = pd.Timestamp(d).normalize()
            if not (as_of < d <= horizon):
                continue
            upcoming.append({"ticker": t, "date": d.date().isoformat(),
                             "session": _SESSION_MAP.get(str(row.get("next_time") or ""),
                                                         "unknown")})
    upcoming.sort(key=lambda r: (r["date"], r["ticker"]))

    return ({"n_members": len(members), "n_reported": len(latest),
             "n_upcoming_14d": len(upcoming), "next": upcoming[:MAX_NEXT]},
            latest)


def _results(members: list[str], latest: dict[str, dict]) -> dict:
    """Beat / miss / inline rollup over the members' latest in-season surprise.

    Resolution-conditioned-denominator law: n_beat + n_miss + n_inline + n_no_data always
    equals n_members. A member with no usable surprise is COUNTED as no-data; it never
    shrinks the denominator the shares would be read against."""
    n_beat = n_miss = n_inline = 0
    for t in members:
        e = latest.get(t)
        sp = None if e is None else e.get("surprise_pct")
        if sp is None or not np.isfinite(float(sp)):
            continue
        sp = float(sp)
        if sp > 0:
            n_beat += 1
        elif sp < 0:
            n_miss += 1
        else:
            n_inline += 1
    n_reported = n_beat + n_miss + n_inline
    if n_reported < MIN_REPORTED:
        return {"n_beat": None, "n_miss": None, "n_inline": None,
                "n_no_data": len(members), "beat_basis": BEAT_BASIS_REFUSED}
    return {"n_beat": n_beat, "n_miss": n_miss, "n_inline": n_inline,
            "n_no_data": len(members) - n_reported, "beat_basis": BEAT_BASIS}


def _guidance(members: list[str], hits: pd.DataFrame | None) -> dict:
    """engine.guidance_gap's classifier, generalized to an arbitrary basket roster.

    The rollup, the latest-direction-per-ticker resolution, and the band ladder are the
    IMPORTED functions — this wrapper only supplies the member filter and converts
    guidance_gap's below-floor NEUTRAL into an explicit null. Its >=MIN_FILERS distinct-
    filers law is imported too, so the two can never drift apart."""
    from engine import guidance_gap as gg
    empty = {"band": None, "n_filers": 0, "basis": GUIDANCE_BASIS}
    if hits is None or hits.empty:
        return empty
    mh = hits[hits["ticker"].astype(str).isin(set(members))]
    if mh.empty:
        return empty
    try:
        rolled = gg._theme_guidance("basket", mh)
    except Exception as e:  # noqa: BLE001 — one basket failing never blocks the sweep
        log.warning("group_earnings: guidance rollup failed: %s", e)
        return empty
    if rolled is None:
        return empty
    n_filers = int(rolled["n_raisers"]) + int(rolled["n_cutters"])
    band = rolled["guidance_band"] if n_filers >= gg.MIN_FILERS else None
    return {"band": band, "n_filers": n_filers, "basis": GUIDANCE_BASIS}


def _revisions_block(members: list[str], rev: pd.DataFrame | None) -> dict:
    """Share of covered members with net-UP analyst revisions (theme_revisions pattern).

    Coverage gate is engine.theme_revisions.MIN_ANALYSTS, imported so it cannot drift from
    the theme-level rollup. Below MIN_COVERED covered members the share nulls — n_covered
    is still printed, so the refusal is visible rather than silent."""
    from engine.theme_revisions import MIN_ANALYSTS
    if rev is None or rev.empty or "breadth" not in rev.columns:
        return {"net_up_share": None, "n_covered": 0}
    present = [t for t in members if t in rev.index]
    if not present:
        return {"net_up_share": None, "n_covered": 0}
    rows = rev.loc[present]
    if isinstance(rows, pd.Series):
        rows = rows.to_frame().T
    if "n_analysts" in rows.columns:
        rows = rows[pd.to_numeric(rows["n_analysts"], errors="coerce") >= MIN_ANALYSTS]
    b = pd.to_numeric(rows["breadth"], errors="coerce").dropna()
    n_covered = int(len(b))
    if n_covered < MIN_COVERED:
        return {"net_up_share": None, "n_covered": n_covered}
    return {"net_up_share": round(float((b > 0).mean()), 3), "n_covered": n_covered}


def _drift(members: list[str], latest: dict[str, dict], closes: pd.DataFrame,
           spy: pd.Series, sessions: pd.DatetimeIndex) -> dict:
    """Share of this season's reporters whose SPY-adjusted return over the DRIFT_SESSIONS
    sessions AFTER the reaction close is positive. Measured from the reaction session's
    close, so the initial gap is excluded and this is drift, not reaction."""
    last_i = len(sessions) - 1
    vals: list[float] = []
    for t in members:
        e = latest.get(t)
        if e is None or t not in closes.columns:
            continue
        i = int(sessions.searchsorted(e["event_date"], side="left"))
        if i >= len(sessions) or sessions[i] != e["event_date"]:
            continue
        j = i + DRIFT_SESSIONS
        if j > last_i:
            continue
        p0, p1 = closes[t].iloc[i], closes[t].iloc[j]
        s0, s1 = spy.iloc[i], spy.iloc[j]
        if not all(pd.notna(x) and float(x) > 0 for x in (p0, p1, s0, s1)):
            continue
        vals.append(float(p1 / p0 - 1.0) - float(s1 / s0 - 1.0))
    n = len(vals)
    if n < MIN_DRIFT_N:
        return {"pos_share_5d": None, "n": n}
    return {"pos_share_5d": round(float(np.mean([v > 0 for v in vals])), 3), "n": n}


def _null_sympathy(n_events: int = 0, n_reporters: int = 0) -> dict:
    return {"ratio": None, "n_events": n_events, "n_reporters": n_reporters,
            "window_q": WINDOW_Q, "basis": SYMPATHY_BASIS,
            "directional": {"beat_day_median": None, "miss_day_median": None,
                            "n_beat_days": 0, "n_miss_days": 0}}


def sympathy(members: list[str], events: dict[str, list[dict]], adj: pd.DataFrame,
             sessions: pd.DatetimeIndex) -> tuple[dict, list[dict]]:
    """Do earnings move this basket together?

    Returns (block, ledger_rows). `adj` is the SPY-adjusted daily return matrix; only the
    window's tail is passed in. See the module DISCLOSED RULES for the full definition —
    in short: pooled |non-reporter moves| on member report days, over the same members'
    median |move| on every session that is NOT a report day for ANY member."""
    cols = [t for t in members if t in adj.columns]
    if len(cols) < MIN_COHORT + 1 or len(sessions) == 0:
        return _null_sympathy(), []
    block = adj[cols]

    # every session that any member reports into — both the event set and the sessions the
    # baseline must EXCLUDE (a baseline that kept them would be contaminated by the very
    # moves the ratio is supposed to stand out against)
    per_day: dict[pd.Timestamp, list[dict]] = {}
    for t in cols:
        for e in events.get(t, []):
            d = e["event_date"]
            if d in block.index:
                per_day.setdefault(d, []).append({"ticker": t, **e})
    report_days = set(per_day)

    pooled_abs: list[float] = []
    beat_signed: list[float] = []
    miss_signed: list[float] = []
    n_beat_days = n_miss_days = 0
    reporters: set[str] = set()
    n_events = 0
    rows: list[dict] = []

    for d in sorted(per_day):
        reporting = {r["ticker"] for r in per_day[d]}
        cohort_cols = [t for t in cols if t not in reporting]
        if len(cohort_cols) < MIN_COHORT:
            continue
        moves = pd.to_numeric(block.loc[d, cohort_cols], errors="coerce").dropna()
        moves = moves[np.isfinite(moves)]
        if len(moves) < MIN_COHORT:
            continue
        abs_moves = moves.abs()
        med_abs = float(abs_moves.median())
        med_signed = float(moves.median())
        pooled_abs.extend(abs_moves.tolist())
        day_rows = []
        for r in per_day[d]:
            n_events += 1
            reporters.add(r["ticker"])
            sp = r.get("surprise_pct")
            sign = None
            if sp is not None and np.isfinite(float(sp)):
                sign = 1 if float(sp) > 0 else (-1 if float(sp) < 0 else 0)
            day_rows.append({"event_date": d.date().isoformat(),
                             "reporter_ticker": r["ticker"], "surprise_sign": sign,
                             "n_cohort": int(len(moves)),
                             "cohort_median_abs_move": med_abs,
                             "cohort_median_signed_move": med_signed})
        rows.extend(day_rows)
        # directional split is per EVENT DAY, keyed off the reporters' surprise signs; a
        # day with both a beat and a miss reporting is ambiguous and counts for neither
        signs = {r["surprise_sign"] for r in day_rows} - {None}
        if signs == {1}:
            n_beat_days += 1
            beat_signed.extend(moves.tolist())
        elif signs == {-1}:
            n_miss_days += 1
            miss_signed.extend(moves.tolist())

    if n_events < MIN_SYMPATHY_EVENTS or len(reporters) < MIN_SYMPATHY_REPORTERS:
        return _null_sympathy(n_events, len(reporters)), rows

    baseline_idx = [d for d in block.index if d not in report_days]
    base = block.loc[baseline_idx].abs().to_numpy(dtype=float).ravel()
    base = base[np.isfinite(base)]
    ratio = None
    if len(base) and len(pooled_abs):
        b = float(np.median(base))
        if b > 0:
            ratio = round(float(np.median(pooled_abs)) / b, 2)

    return ({"ratio": ratio, "n_events": n_events, "n_reporters": len(reporters),
             "window_q": WINDOW_Q, "basis": SYMPATHY_BASIS,
             "directional": {
                 "beat_day_median": (round(float(np.median(beat_signed)), 5)
                                     if n_beat_days >= MIN_DIRECTIONAL_DAYS and beat_signed
                                     else None),
                 "miss_day_median": (round(float(np.median(miss_signed)), 5)
                                     if n_miss_days >= MIN_DIRECTIONAL_DAYS and miss_signed
                                     else None),
                 "n_beat_days": n_beat_days, "n_miss_days": n_miss_days}},
            rows)


# ---------------------------------------------------------------------------
# Sweep
# ---------------------------------------------------------------------------

def compute_group_earnings(write_ledger: bool = True) -> dict | None:
    """One `group_earnings_pulse.v1` object per US basket, keyed by basket_id.

    CONTEXT-ONLY. Returns None when the registry or the price grid is unavailable — the
    nightly then publishes no earnings_pulse.json rather than a fabricated one."""
    mem = _membership()
    if not mem or not mem.get("baskets"):
        return None
    bdict = mem["baskets"]
    items = list(bdict.items()) if isinstance(bdict, dict) else [(b["id"], b) for b in bdict]
    if not items:
        return None

    all_tickers = sorted({m["ticker"] for _bid, b in items
                          for m in (b.get("members") or []) if m.get("ticker")})
    closes = _member_closes(all_tickers)
    if closes.empty:
        return None
    sessions = pd.DatetimeIndex(closes.index)
    as_of = sessions.max()
    spy = _spy_close(sessions)
    if spy is None or spy.dropna().empty:
        return None

    earn, eightk, rev = _earnings_store(), _eightk_results(), _revisions()
    try:
        from engine import guidance_gap as gg
        hits = gg._hits()
        if hits is not None and not hits.empty:
            hits = hits.copy()
            hits["file_date"] = pd.to_datetime(hits["file_date"], errors="coerce")
            hits = hits.dropna(subset=["file_date"])
            cutoff = pd.Timestamp(as_of.date() - timedelta(days=gg.RECENT_DAYS))
            hits = hits[hits["file_date"] >= cutoff]
    except Exception as e:  # noqa: BLE001 — guidance is a leg, never the build
        log.warning("group_earnings: guidance hits unavailable: %s", e)
        hits = None

    # SPY-adjusted daily returns, computed ONCE for every member in the registry
    rets = closes.pct_change(fill_method=None)
    spy_ret = spy.pct_change(fill_method=None)
    adj = rets.sub(spy_ret, axis=0)

    win = min(len(sessions), WINDOW_Q * SESSIONS_PER_QUARTER)
    win_sessions = sessions[-win:]
    adj_win = adj.loc[win_sessions]

    events = build_report_events(all_tickers, sessions, earn, eightk)
    generated_at = datetime.now(timezone.utc).isoformat()
    as_of_s = as_of.date().isoformat()

    out: dict[str, dict] = {}
    ledger_rows: list[dict] = []
    for bid, b in items:
        try:
            members = _live_members(b, as_of)
            if not members:
                continue
            season, latest = _season(members, events, earn, sessions, as_of)
            symp, rows = sympathy(members, events, adj_win, win_sessions)
            for r in rows:
                ledger_rows.append({"basket_id": str(bid), **r})
            out[str(bid)] = {
                "schema": SCHEMA,
                "authority": AUTHORITY,
                "generated_at": generated_at,
                "basket_id": str(bid),
                "as_of": as_of_s,
                "season": season,
                "results": _results(members, latest),
                "guidance": _guidance(members, hits),
                "revisions": _revisions_block(members, rev),
                "drift": _drift(members, latest, closes, spy, sessions),
                "sympathy": symp,
            }
        except Exception as e:  # noqa: BLE001 — one basket never blocks the other 47
            log.warning("group_earnings[%s] failed: %s", bid, e)
            continue

    if not out:
        return None
    if write_ledger:
        try:
            append_sympathy_ledger(ledger_rows)
        except Exception as e:  # noqa: BLE001 — the ledger is never fatal to the build
            log.warning("group_earnings sympathy ledger append failed: %s", e)
    return out


# ---------------------------------------------------------------------------
# Sympathy ledger — append-only, nightly-lane only
# ---------------------------------------------------------------------------

LEDGER_COLUMNS = ["basket_id", "event_date", "reporter_ticker", "surprise_sign",
                  "n_cohort", "cohort_median_abs_move", "cohort_median_signed_move",
                  "advanced_at"]
LEDGER_KEY = ["basket_id", "event_date", "reporter_ticker"]


def sympathy_ledger_path():
    return config.data_dir() / "group_pulse" / "sympathy.parquet"


def _normalise_ledger(df: pd.DataFrame) -> pd.DataFrame:
    """Stable dtypes so an append never re-types (and so re-writes an existing row)."""
    df = df.reindex(columns=LEDGER_COLUMNS)
    for c in ("basket_id", "event_date", "reporter_ticker", "advanced_at"):
        df[c] = df[c].astype("string")
    df["surprise_sign"] = pd.to_numeric(df["surprise_sign"], errors="coerce").astype("Int64")
    df["n_cohort"] = pd.to_numeric(df["n_cohort"], errors="coerce").astype("Int64")
    for c in ("cohort_median_abs_move", "cohort_median_signed_move"):
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("float64")
    return df


def read_sympathy_ledger() -> pd.DataFrame | None:
    p = sympathy_ledger_path()
    if not p.exists():
        return None
    try:
        return pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("group_earnings: sympathy ledger unreadable: %s", e)
        return None


def append_sympathy_ledger(rows: list[dict]) -> int:
    """Append NEW (basket_id, event_date, reporter_ticker) rows. Returns rows written.

    Rows are historical facts and IMMUTABLE once written: an existing key is skipped, never
    updated, and when nothing is new the file is left untouched byte-for-byte. Lane-gated
    (house law: the nightly is the sole advancer of forward ledgers) — an intraday or
    express lane computes the pulse and discards the write."""
    if not _ledger_advance_enabled():
        return 0
    if not rows:
        return 0
    existing = read_sympathy_ledger()
    seen: set[tuple] = set()
    if existing is not None and not existing.empty and set(LEDGER_KEY).issubset(existing.columns):
        seen = {tuple(str(v) for v in t)
                for t in existing[LEDGER_KEY].itertuples(index=False, name=None)}
    ts = datetime.now(timezone.utc).isoformat()
    fresh = []
    for r in rows:
        key = (str(r.get("basket_id")), str(r.get("event_date")), str(r.get("reporter_ticker")))
        if key in seen:
            continue
        seen.add(key)
        fresh.append({**r, "advanced_at": ts})
    if not fresh:
        return 0                                  # nothing new -> the file is not rewritten
    add = _normalise_ledger(pd.DataFrame(fresh))
    out = add if existing is None or existing.empty else pd.concat(
        [_normalise_ledger(existing), add], ignore_index=True)
    out = out.sort_values(LEDGER_KEY, kind="stable").reset_index(drop=True)
    p = sympathy_ledger_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(p, index=False)
    return len(fresh)


def write_earnings_pulse(out_dir) -> dict | None:
    """Compute the sweep and write <out_dir>/earnings_pulse.json. None on shortfall."""
    from pathlib import Path
    pulse = compute_group_earnings()
    if not pulse:
        return None
    d = Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    (d / "earnings_pulse.json").write_text(
        json.dumps(pulse, separators=(",", ":"), default=str))
    return pulse
