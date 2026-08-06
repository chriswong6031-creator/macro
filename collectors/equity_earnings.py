"""Per-stock earnings calendar + surprise history (Phase 2 of
research/STOCK_FUNDAMENTALS_PLAN.md).

Nasdaq's public JSON is the one free source that gives, for the whole US universe:
  next earnings DATE   api.nasdaq.com/api/calendar/earnings?date=YYYY-MM-DD
                       (date-keyed → a ~6-week sweep of weekdays covers everyone in
                        ~30 calls; the earliest hit per ticker is its next report)
  SURPRISE history     api.nasdaq.com/api/company/{sym}/earnings-surprise
                       (last 4 quarters: actual EPS vs consensus + surprise %)

It is UNOFFICIAL and Akamai bot-walled, so: a browser User-Agent, and a CI CANARY —
if the first calendar call is blocked (403/empty), we log and return the existing
cache untouched rather than spend the run hammering a wall. Best-effort, resumable
(surprise history dripped + capped), never fatal to the build.

Writes data/earnings/earnings.parquet (ticker-indexed: next_date, next_time,
eps_forecast, surprises_json, surprises_as_of, as_of). engine/stock_fundamentals reads
it for the Earnings panel (countdown + beat/miss table). Honest caveat (on the page):
dates are estimated and can move; data is community/Nasdaq-sourced, not official
guidance.

ENTRY POINT — `python -m collectors.equity_earnings` (the nightly line in daily.yml's
collect_tail job) sweeps the WHOLE universe: the S&P 500+400+600 breadth union PLUS the
Hot Tape liquid names (data/marketing/hot_tape_pack.json — the calendar sweep is
date-keyed, so the wider set costs zero extra requests). Named tickers are a smoke-test
opt-in and must be passed explicitly: `--tickers AAPL NVDA JPM`. This is load-bearing:
the no-arg path used to fall through to a 3-name demo default, which pinned the nightly
to a 3-ticker universe for six weeks (1361 of 1364 rows frozen at as_of 2026-06-19)
while the store-level freshness tripwire read green off the 3 fresh rows.

AS_OF CONTRACT — one sweep, one stamp. A successful full-universe sweep at or above
MIN_SWEEP_COVERAGE re-stamps every row with the run's single `now`; consumers may read
the store's as_of as a file-level freshness anchor. Only a partial refresh (smoke run,
or a sweep below the coverage floor) leaves mixed per-row stamps — deliberately, as the
honest signature of a partial refresh.

ROTATION CONTRACT (W4) — the calendar sweep is free, but the surprise-history drip is
budgeted (`max_new`, default 120/run). That budget is served OLDEST-STAMP-FIRST
(`drip_order`), never alphabetically: an alphabetical head plus a REFRESH_DAYS re-stale
clock is a starvation loop, not a rotation (see drip_order's docstring for the arithmetic
that leaves the tail of the alphabet permanently un-dripped).

STALENESS ALARM (W4) — every run ends by grading the SHARE of the store that has aged past
the 10-trading-day mark where engine/earnings_blackout.assess starts failing open, plus any
row reporting within 5 sessions. That is the exact silence W4 was chartered to break: on
2026-08-03 PLTR's row held the right date (next_date=2026-08-03) and the veto still no-opped
on it, because as_of=2026-06-19 made the row stale and the fail-open law returned
in_blackout=False without a word. The veto's fail-open semantics are DELIBERATELY unchanged;
the alarm is the fix for the silence.
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import date as _date, datetime, timedelta, timezone

import pandas as pd

from engine.earnings_catalyst import as_date as _as_date, trading_days_between as _td_between
from lib import config

log = logging.getLogger(__name__)

CALENDAR = "https://api.nasdaq.com/api/calendar/earnings?date={}"
SURPRISE = "https://api.nasdaq.com/api/company/{}/earnings-surprise"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*", "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.nasdaq.com", "Referer": "https://www.nasdaq.com/",
}
SWEEP_DAYS = 66           # weekdays (~a full quarter) so every name's next report lands
REFRESH_DAYS = 7
#: A ~quarter-long sweep should place nearly every universe name (1363 of 1506 on the
#: last known-good full run, 2026-06-19). Below this share of the universe the sweep is
#: broken, not quiet — every name it missed keeps its previous as_of, so the store rots
#: silently. Deliberately loose: it fires on a break, not on a slow earnings week.
MIN_SWEEP_COVERAGE = 0.50

#: W4 staleness alarm. STALE_AGE_TD mirrors engine.earnings_blackout._STALE_AGE_TD — the
#: alarm must fire at exactly the age where the veto starts failing open, or it is grading
#: a different question than the one that hurt. STALE_SHARE_ALARM is deliberately far below
#: MIN_SWEEP_COVERAGE's inverse: coverage grades THIS RUN's reach, staleness grades the
#: STORE's accumulated rot, and a store can pass every nightly coverage check while a fifth
#: of it quietly ages out (the 2026-08-04 shape: 1,117 rows fresh, 835 still at 06-19).
STALE_AGE_TD = 10
STALE_SHARE_ALARM = 0.20
IMMINENT_REPORT_TD = 5


def _cache_path():
    p = config.data_dir() / "earnings" / "earnings.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _safe_json_list(s) -> list:
    """json.loads(s) as a list, or [] — never raises."""
    try:
        v = json.loads(s or "[]")
    except (TypeError, ValueError):
        return []
    return v if isinstance(v, list) else []


def _num(x) -> float | None:
    try:
        v = float(str(x).replace("$", "").replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None
    return v if v == v else None


def _get_json(session, url: str, retries: int = 2):
    for attempt in range(retries):
        try:
            r = session.get(url, timeout=20)
            if r.status_code == 403:
                return "blocked"
            r.raise_for_status()
            if "json" not in r.headers.get("content-type", ""):
                return None
            return r.json()
        except Exception as e:  # noqa: BLE001
            if attempt == retries - 1:
                log.debug("nasdaq GET failed %s: %s", url[-40:], e)
                return None
            time.sleep(1.0 * (attempt + 1))
    return None


def _universe() -> set[str]:
    """Index union (S&P 500+400+600) ∪ the Hot Tape liquid names.

    The calendar sweep is DATE-keyed (66 calls total, each returning every name
    reporting that day), so widening the universe costs zero extra calendar
    requests — membership only decides which returned rows are kept. The Hot
    Tape context pack (data/marketing/hot_tape_pack.json, ~1,300 liquid names)
    is the marketing supply program's universe (TrendSpider masterplan): its
    non-index names (recent IPOs, liquid mid/small caps) need earnings-week
    context too. Fail-open: an absent/unreadable pack leaves the index union.
    """
    out: set[str] = set()
    for grp in ("breadth", "smallcap_breadth", "midcap_breadth"):
        p = config.data_dir() / grp / "constituents.parquet"
        if p.exists():
            out.update(str(t) for t in pd.read_parquet(p).index)
    try:
        pack = json.loads((config.data_dir() / "marketing" / "hot_tape_pack.json").read_text())
        out.update(str(t).upper() for t in (pack.get("tickers") or {}))
    except (OSError, ValueError):
        pass
    return out


def _calendar_sweep(session, universe: set[str]) -> tuple[dict, bool]:
    """{ticker: {next_date, next_time, eps_forecast}} from the upcoming weekday
    calendars. Returns ({}, blocked=True) if the first call is bot-walled."""
    out: dict[str, dict] = {}
    d = datetime.now(timezone.utc).date()
    checked = 0
    first = True
    while checked < SWEEP_DAYS:
        if d.weekday() < 5:                       # weekdays only
            data = _get_json(session, CALENDAR.format(d.isoformat()))
            if first:
                first = False
                if data == "blocked":
                    return {}, True               # CI canary: bot-walled → bail
            rows = ((data or {}).get("data") or {}).get("rows") or [] if data != "blocked" else []
            for r in rows:
                sym = (r.get("symbol") or "").upper()
                if sym and sym in universe and sym not in out:
                    out[sym] = {"next_date": d.isoformat(), "next_time": r.get("time"),
                                "eps_forecast": _num(r.get("epsForecast"))}
            checked += 1
            time.sleep(0.25)
        d += timedelta(days=1)
    return out, False


def _surprises(session, sym: str) -> list[dict]:
    data = _get_json(session, SURPRISE.format(sym))
    if not data or data == "blocked":
        return []
    rows = ((data.get("data") or {}).get("earningsSurpriseTable") or {}).get("rows") or []
    out = []
    for r in rows:
        out.append({"qtr": r.get("fiscalQtrEnd"), "reported": r.get("dateReported"),
                    "eps": _num(r.get("eps")), "consensus": _num(r.get("consensusForecast")),
                    "surprise_pct": _num(r.get("percentageSurprise"))})
    return out


def _stamp_of(stamps, ticker: str) -> str | None:
    """A ticker's previous surprise stamp as a sortable ISO string, or None.

    Accepts a pandas Series (the store column) or a plain dict.  Anything that is
    missing, NaN, or not ISO-shaped comes back None and is treated as NEVER-DRIPPED —
    fail-safe in the right direction: an unreadable stamp buys a name a place at the
    FRONT of the queue (one cheap re-fetch), never a permanent seat at the back.
    """
    try:
        v = stamps.get(ticker) if stamps is not None else None
    except Exception:  # noqa: BLE001 — a malformed store must not break the ordering
        return None
    if v is None or v != v:                       # NaN-safe
        return None
    s = str(v)
    # `as_of`/`surprises_as_of` are always datetime.now(timezone.utc).isoformat(), so
    # every stamp shares one format and lexicographic order IS chronological order.
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s
    return None


def drip_order(candidates, stamps) -> list[str]:
    """Order the budgeted surprise-history drip OLDEST-STAMP-FIRST.

    THE STARVATION THIS FIXES.  The drip used to take ``sorted(cal)[:max_new]`` — the
    ALPHABETICAL head of the stale set.  Pair that with ``stale()``'s REFRESH_DAYS=7
    re-stale clock and the queue is not a rotation, it is a treadmill:

        night 1   names   1-120 (alphabetical) dripped
        ...
        night 7   names 721-840 dripped
        night 8   names   1-120 are 7 days old again → stale again → and they still
                  sort FIRST, so the budget goes back to them

    The frontier stops at ~REFRESH_DAYS x max_new names (~840 of a ~1,500-name
    universe) and everything alphabetically past it — roughly ticker "S" onward —
    is never dripped at all, forever.  Nothing in the store shows this: those rows
    carry a fresh calendar ``as_of`` (the cheap sweep re-stamps them nightly) with
    surprise history that is empty or months old.

    Oldest-first makes it a strict rotation: the longest-waiting name is served
    first, so the worst-case wait for any name is bounded by
    ``ceil(len(candidates) / max_new)`` nights instead of being unbounded.
    Never-dripped names sort ahead of every dated one, and ties break on ticker so
    the order is deterministic (a set's iteration order never leaks in).
    """
    return sorted(candidates,
                  key=lambda t: (_stamp_of(stamps, t) is not None,
                                 _stamp_of(stamps, t) or "",
                                 t))


def assess_staleness(df, today: _date | None = None,
                     *, stale_age_td: int = STALE_AGE_TD,
                     imminent_td: int = IMMINENT_REPORT_TD) -> dict:
    """Grade the STORE (not the run) for rows that have aged out of usefulness.

    A row is stale when its ``as_of`` is older than ``stale_age_td`` trading days —
    the exact threshold at which ``engine.earnings_blackout.assess`` stops trusting
    the row and silently returns ``in_blackout=False``.  A row is *imminent* when its
    ``next_date`` is inside ``imminent_td`` sessions and has not passed; an imminent
    row that is also stale is the PLTR-class failure and alarms on its own, at any
    share, because one such row is one silent no-op on the day it mattered.

    Returns ``{total, stale, stale_share, imminent, imminent_stale, should_warn}``.
    Never raises: an unreadable frame grades as zero rows and does not warn (the
    empty-sweep annotation in ``main`` owns that case).
    """
    out = {"total": 0, "stale": 0, "stale_share": 0.0,
           "imminent": 0, "imminent_stale": 0, "should_warn": False}
    if df is None or getattr(df, "empty", True) or "as_of" not in getattr(df, "columns", []):
        return out
    ref = today or datetime.now(timezone.utc).date()
    next_dates = df["next_date"] if "next_date" in df.columns else None
    total = stale_n = imminent = imminent_stale = 0
    for i, (_t, as_of) in enumerate(df["as_of"].items()):
        total += 1
        d = _as_date(as_of)
        # An unparseable/absent stamp cannot be shown to be fresh, so it counts stale.
        row_stale = (d is None) or (_td_between(d, ref) > stale_age_td)
        if row_stale:
            stale_n += 1
        if next_dates is not None:
            nd = _as_date(next_dates.iloc[i])
            if nd is not None and 0 <= _td_between(ref, nd) <= imminent_td:
                imminent += 1
                if row_stale:
                    imminent_stale += 1
    share = (stale_n / total) if total else 0.0
    out.update(total=total, stale=stale_n, stale_share=share,
               imminent=imminent, imminent_stale=imminent_stale,
               should_warn=bool(total and (share > STALE_SHARE_ALARM or imminent_stale > 0)))
    return out


def _emit_staleness_annotation(df, today: _date | None = None) -> dict:
    """Emit the W4 staleness alarm when the post-sweep store has rotted.

    House law: `::warning` must START the line, so this is a BARE `print(..., flush=True)`
    and never `log.warning(...)` — every builder here logs with a level-prefixing format,
    which would emit "WARNING ::warning ..." and GitHub would silently drop it (guarded by
    tests/test_gh_annotation_line_start.py, which scans collectors/).
    """
    rep = assess_staleness(df, today)
    if rep["should_warn"]:
        print(f"::warning title=earnings-staleness::{rep['stale']}/{rep['total']} rows "
              f"stale (as_of older than {STALE_AGE_TD} trading days), "
              f"{rep['imminent_stale']} imminent-report rows stale "
              f"(next_date within {IMMINENT_REPORT_TD} trading days) — "
              f"earnings_blackout.assess fails OPEN on every one of them", flush=True)
    return rep


def _emit_coverage_annotation(total: int, universe_n: int, swept_n: int,
                              blocked: bool = False) -> None:
    """Emit a GitHub annotation when the sweep did not refresh most of the universe.

    House law: `::warning` must START the line, so this is a BARE `print(..., flush=True)`
    and never `log.warning(...)` — every builder here logs with a level-prefixing format,
    which would emit "WARNING ::warning ..." and GitHub would silently drop it. `flush` is
    load-bearing because stdout is block-buffered when piped in CI.
    """
    if blocked:
        print(f"::warning title=earnings-calendar-stale::Nasdaq calendar bot-walled "
              f"(likely CI IP) — cache kept untouched at {total} rows; 0 of {universe_n} "
              f"universe names refreshed this run", flush=True)
        return
    cov = (swept_n / universe_n) if universe_n else 0.0
    if cov < MIN_SWEEP_COVERAGE:
        print(f"::warning title=earnings-calendar-stale::calendar sweep refreshed only "
              f"{swept_n} of {universe_n} universe names ({cov:.1%} < "
              f"{MIN_SWEEP_COVERAGE:.0%} floor) — the other rows in the {total}-row store "
              f"keep their previous as_of and will age out of downstream freshness "
              f"ceilings", flush=True)


def fetch_earnings(force: bool = False, max_new: int = 120,
                   tickers: list[str] | None = None) -> pd.DataFrame:
    """Sweep the calendar (cheap, whole universe) + drip surprise history (capped).
    Best-effort + bot-wall-aware: returns the existing cache untouched if blocked."""
    import requests
    cache = _cache_path()
    existing = pd.read_parquet(cache) if cache.exists() else pd.DataFrame()
    universe = set(tickers) if tickers else _universe()
    if not universe:
        return existing

    session = requests.Session()
    session.headers.update(HEADERS)

    cal, blocked = _calendar_sweep(session, universe)
    if blocked:
        log.warning("equity_earnings: Nasdaq calendar bot-walled (likely CI IP) — keeping cache")
        _emit_coverage_annotation(len(existing), len(universe), 0, blocked=True)
        # A bot-walled run is exactly when the store rots, so grade it here too: the
        # coverage annotation says "0 names refreshed", the staleness alarm says how
        # much of the standing cache that has already cost us.
        _emit_staleness_annotation(existing)
        return existing
    log.info("equity_earnings: calendar sweep found next dates for %d of %d universe names",
             len(cal), len(universe))
    _emit_coverage_annotation(max(len(existing), len(cal)), len(universe), len(cal))

    now = datetime.now(timezone.utc).isoformat()
    have_surp = (existing["surprises_json"] if (not existing.empty and "surprises_json" in existing.columns)
                 else pd.Series(dtype=object))

    # surprise history: refresh stale/uncached names, capped.
    # Keyed on surprises_as_of, NOT as_of. `as_of` is re-stamped for every name the CHEAP
    # calendar sweep touches, so gating the EXPENSIVE surprise drip on it would freeze
    # surprise history the moment a full-universe sweep works: ~70-90% of names would look
    # "fresh" every night and the drip would never pick anyone up again.
    prev_surp_asof = (existing["surprises_as_of"]
                      if (not existing.empty and "surprises_as_of" in existing.columns)
                      else pd.Series(dtype=object))

    def _held_surprises(t: str) -> bool:
        """True when the store already holds a non-empty surprise history for t."""
        try:
            return bool(json.loads((have_surp.get(t) if t in have_surp.index else None) or "[]"))
        except (TypeError, ValueError):
            return False

    def stale(t: str) -> bool:
        if force or existing.empty or t not in existing.index:
            return True
        ts = prev_surp_asof.get(t) if t in prev_surp_asof.index else None
        if ts is None or ts != ts:            # absent column or NaN → no surprise stamp
            # Never dripped if we hold no history either — a fresh calendar as_of says
            # nothing about surprises. Only a store that predates surprises_as_of AND
            # already carries history may fall back to as_of as a proxy clock.
            if not _held_surprises(t):
                return True
            ts = existing.loc[t].get("as_of")
        try:
            return (datetime.now(timezone.utc) - pd.to_datetime(ts)).days > REFRESH_DAYS
        except Exception:  # noqa: BLE001
            return True
    # PERSIST the cheap calendar next_date for EVERY name the sweep found — not only the capped
    # surprise-drip batch (the bug: a 1363-name sweep wrote 4). Carry forward existing surprise
    # history so the per-name drip below only adds detail, never drops the calendar.
    out = pd.DataFrame([
        {"ticker": t, "next_date": cc.get("next_date"), "next_time": cc.get("next_time"),
         "eps_forecast": cc.get("eps_forecast"),
         "surprises_json": (have_surp.get(t) if t in have_surp.index else "[]"),
         "surprises_as_of": (prev_surp_asof.get(t) if t in prev_surp_asof.index else None),
         "as_of": now}
        for t, cc in cal.items()
    ]).set_index("ticker") if cal else pd.DataFrame()
    # keep any previously-cached names this sweep didn't cover
    if not existing.empty:
        keep = existing[~existing.index.isin(out.index)] if not out.empty else existing
        out = pd.concat([out, keep]) if not out.empty else existing

    # surprise history: drip a capped batch of stale/uncached names (the only expensive call).
    # ROTATION (W4): oldest surprises_as_of first — see drip_order for why the previous
    # `sorted(cal)` alphabetical head starved the tail of the universe permanently.
    todo = drip_order(
        [t for t in (tickers or cal or universe) if stale(t) and t in out.index],
        prev_surp_asof,
    )[:max_new]
    if "surprises_as_of" not in out.columns and not out.empty:
        out["surprises_as_of"] = None
    for t in todo:
        out.loc[t, "surprises_json"] = json.dumps(_surprises(session, t))
        out.loc[t, "surprises_as_of"] = now
        out.loc[t, "as_of"] = now
        time.sleep(0.25)
    # SINGLE-STAMP (standing law: one freshness anchor key, one writer, one stamp).
    # A certified full-universe sweep re-stamps EVERY row — including carried-forward
    # names the calendar returned no row for, because "absent from the whole 66-weekday
    # forward calendar" is itself an observation made at `now` (no report scheduled in
    # the window). Without this, carried-forward rows keep old stamps and the store ships
    # a MIXED-as_of file that forces every consumer to gate per row (the 2026-08-02
    # two-stamp file: 1361 rows at 06-19 beside 3 at 07-28).
    # Guarded three ways, because a uniform stamp on a partial refresh would certify rot
    # as freshness (exactly how the 06-19 freeze hid behind a max()-based tripwire):
    #   - full-universe path only (a --tickers smoke run touches a subset; its untouched
    #     rows must keep their honest old stamps),
    #   - never when bot-walled (that path returns above, cache untouched),
    #   - only at >= MIN_SWEEP_COVERAGE (below the floor the mixed stamps ARE the
    #     tripwire, and _emit_coverage_annotation has already fired).
    # surprises_as_of stays per-row on purpose — it is the drip's own clock and gates
    # which names the capped drip picks up next night.
    if tickers is None and universe and (len(cal) / len(universe)) >= MIN_SWEEP_COVERAGE \
            and not out.empty:
        out["as_of"] = now
    if not out.empty:
        out.to_parquet(cache)
    # W4 staleness alarm — graded on the POST-sweep store, so it describes what the
    # next build will actually read. Emitted on every path (smoke runs included: the
    # store's rot is real regardless of which invocation last wrote it).
    _emit_staleness_annotation(out)
    _n_surp = 0
    if not out.empty and "surprises_json" in out.columns:
        _n_surp = int(out["surprises_json"].fillna("[]").apply(
            lambda s: bool(_safe_json_list(s))).sum())
    log.info("equity_earnings: cache now %d tickers (%d with a next date, "
             "%d with surprise history; dripped %d this run)",
             len(out), int(out["next_date"].notna().sum()) if "next_date" in out else 0,
             _n_surp, len(todo))
    return out


DEFAULT_MAX_NEW = 120     # surprise-history drip cap per run (~30s at 0.25s/call)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.  BARE `python -m collectors.equity_earnings` IS THE NIGHTLY.

    Root-cause fix (E8/E5 sweep + #3979, 2026-07-29): this block used to read
        ts = sys.argv[1:] or ["AAPL", "NVDA", "JPM"]
        fetch_earnings(force=True, max_new=len(ts), tickers=ts)
    i.e. a bare invocation ran a THREE-TICKER smoke test — and daily.yml's
    collect_tail step invokes it bare.  So the "~66 weekday, whole-universe"
    sweep the step comment promises had never run in production: the store held
    1361 rows stamped 2026-06-19 and exactly 3 (AAPL/NVDA/JPM — the hardcoded
    smoke list) stamped 2026-07-28.  Nasdaq was never the problem (probed live
    the same day: 305/61/132 calendar rows for 07-30/07-31/08-03, HTTP 200).

    A bare run now sweeps the real `_universe()`.  A smoke test must name its
    tickers explicitly — positional (`python -m collectors.equity_earnings AAPL
    NVDA`) or via `--tickers` (space- and/or comma-separated symbols).  Never
    restore a default ticker list here: any fallback universe silently becomes
    the nightly's universe (the 2026-06-19 freeze shape).
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="US earnings calendar + surprise-history sweep")
    ap.add_argument("tickers", nargs="*", metavar="SYM",
                    help="explicit tickers = SMOKE TEST (default: sweep the full universe)")
    ap.add_argument("--tickers", dest="tickers_flag", nargs="+", metavar="SYM", default=None,
                    help="same smoke path as the positional form; space- and/or "
                         "comma-separated symbols both accepted")
    ap.add_argument("--max-new", type=int, default=DEFAULT_MAX_NEW,
                    help=f"surprise-history drip cap (default {DEFAULT_MAX_NEW})")
    ap.add_argument("--force", action="store_true",
                    help="refresh surprise history regardless of REFRESH_DAYS age")
    args = ap.parse_args(argv)

    raw = list(args.tickers_flag or []) + list(args.tickers or [])
    ts = list(dict.fromkeys(
        sym for tok in raw for sym in (s.strip().upper() for s in tok.split(",")) if sym
    )) or None

    if ts:
        # Smoke path: force + a cap matching the named list — never the nightly
        # (daily.yml invokes this module bare; tests pin tickers=None on that path).
        df = fetch_earnings(force=True, max_new=len(ts), tickers=ts)
        for t in ts:
            if t in df.index:
                r = df.loc[t]
                surp = json.loads(r.get("surprises_json") or "[]")
                print(f"\n{t}: next={r.get('next_date')} ({r.get('next_time')}) "
                      f"est={r.get('eps_forecast')}")
                for s in surp:
                    print(f"   {s['qtr']}: actual {s['eps']} vs est {s['consensus']} "
                          f"→ {s['surprise_pct']}%")
        return 0

    # Production path: whole universe, capped surprise drip.
    df = fetch_earnings(force=args.force, max_new=args.max_new)
    n = len(df)
    if n == 0:
        # Line-start annotation, never through a logger (tests/test_gh_annotation_line_start.py).
        print("::warning title=earnings-sweep-empty::earnings sweep produced zero rows "
              "(bot-wall or empty universe) — the previous cache stands", flush=True)
        return 0
    fresh = 0
    if "as_of" in df.columns:
        today = datetime.now(timezone.utc).date().isoformat()
        fresh = int(df["as_of"].astype(str).str.startswith(today).sum())
    print(f"equity_earnings: swept {n} tickers, {fresh} stamped today", flush=True)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
