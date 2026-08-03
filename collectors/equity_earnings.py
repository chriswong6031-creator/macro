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
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import datetime, timedelta, timezone

import pandas as pd

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

    # surprise history: drip a capped batch of stale/uncached names (the only expensive call)
    todo = [t for t in (tickers or sorted(cal) or list(universe)) if stale(t) and t in out.index][:max_new]
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
