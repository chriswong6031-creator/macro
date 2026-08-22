"""Fetch the baskets-only DEEP OHLCV store the consolidated-index engines render over.

Sibling of scripts/fetch_basket_extras.py. That store is CLOSE-ONLY (the EW level +
perf table need only closes). The consolidated-index engines (engine/basket_index ->
engine/basket_mtf + engine/basket_tape) need full OHLCV per member to build a real
basket CANDLE: open/high/low/close for ATR/Bollinger/vol-hole and VOLUME for whale
accumulation, Chaikin money-flow (net inflow/outflow) and dollar-volume. Only ~21% of
members had volume on disk (data/stocks/*.parquet); the rest were close-only — so this
backfills the gap for EVERY member.

    data/baskets/ohlcv/<TICKER>.parquet   per-ticker [open,high,low,close,volume], deep

Kept SEPARATE from the breadth/factor universe (the free-S&P-1500 invariant) and from
data/stocks (the US-stock-library deep store) so neither is polluted by off-index basket
names. engine/basket_index PREFERS this store, then falls back to data/stocks (already
OHLCV) and the yahoo store (close+volume) for names it lacks — so a flaky pull degrades
gracefully rather than dropping a basket.

Keyless (yfinance), batched, auto-adjusted. Additive and non-fatal: each ticker's fresh
pull is MERGED onto its prior parquet (prior backfills any row the pull missed), so a
flaky day can never drop a member or break the daily build. Wired into scripts/collect.py
after fetch_basket_extras.

Usage:
    python -m scripts.fetch_basket_ohlcv [--limit N]               # the basket membership
    python -m scripts.fetch_basket_ohlcv --tickers NVDA,ANET,...   # an explicit list
    python -m scripts.fetch_basket_ohlcv --finviz idx_ndx,idx_rut  # every name in a
                                                                   # data/finviz_screener/<flt>.json
    python -m scripts.fetch_basket_ohlcv --finviz ... --members    # index universes UNIONED
                                                                   # with the basket membership
    python -m scripts.fetch_basket_ohlcv --finviz ... --store      # ...UNIONED with every
                                                                   # ticker already on disk
    python -m scripts.fetch_basket_ohlcv --census                  # no fetch; store-wide
                                                                   # staleness tripwire only
The explicit/finviz modes back the NDX/Russell subsector desks (the deep store
engine/basket_index prefers also serves their EW subsector indices). An explicit universe
REPLACES the membership default — pass --members to union it back in. The nightly call
must keep membership covered (2026-07-16 incident: PR #776 switched collect.py to
--finviz-only and 528 member files silently froze at 2026-06-29 for 11 sessions while the
aggregate as_of stayed fresh off the NDX/RUT names; check_membership_staleness below is
the per-member tripwire that makes that failure mode visible).

--store EXISTS BECAUSE AN INDEX UNIVERSE SHRINKS (2026-08-20 fetch-universe drift).
The finviz screener JSONs are re-pulled nightly, so a name dropped by an index
reconstitution silently leaves the maintained set — and because nothing ever fetched it
again, its parquet froze on disk FOREVER while `engine/stage_analysis.build_universe()`
kept classifying it (that function globs the store, so it never forgets a ticker).
Measured on 2026-08-20: 183 of 2,782 files were stale, 179 of them outside
`membership ∪ finviz(idx_ndx, idx_rut)`, with 110 frozen on one day — 2026-07-10 — which
is a reconstitution drop-out, not 110 simultaneous delistings. A live vendor probe of that
cluster returned a current tape for 10 of 10 sampled names (ARWR/AXSM/BBIO/BE/AAOI/...),
so the tapes were never dead: they were merely unrequested. --store closes that hole by
making the store SELF-MAINTAINING — every ticker already on disk keeps being fetched, so
leaving an index can no longer freeze a file. The one lawful way out of the fetch universe
is now an EXIT ROW in config/delisted_symbols.yml (lib/delisted_symbols), which this
module subtracts from every derived leg: a security that stopped existing must not be
requested nightly forever. See `check_membership_staleness` for the census that keeps the
two halves honest.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config, delisted_symbols  # noqa: E402
from lib.ticker_aliases import YAHOO_FETCH_ALIASES as ALIASES  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("fetch_basket_ohlcv")

# Deep enough that the MONTHLY MTF timeframe (engine.cycles needs ~900 trading days ≈
# 3.6y of month-end bars) resolves for any member with a long-enough listing.
START = "2014-01-01"
RETRIES = 4
BACKOFF_S = 3.0
BATCH = 40                  # tickers per yfinance download call (5 OHLCV fields each)
COLS = ["open", "high", "low", "close", "volume"]

# Ticker renames where the vendor symbol differs from the membership ticker live in
# lib/ticker_aliases (imported above as ALIASES) — ONE map shared with the close-only
# sibling scripts/fetch_basket_extras. It used to be a second local copy here, which is
# why MMC (Marsh McLennan, renamed MMC->MRSH on 2026-01-14) was fetched by extras but
# never by this deep store: no data/baskets/ohlcv/MMC.parquet ever existed.


def _membership_rows() -> list[dict]:
    p = config.data_dir() / "baskets" / "membership.json"
    if not p.exists():
        return []
    mem = json.loads(p.read_text())
    bdict = mem.get("baskets") or {}
    items = bdict.values() if isinstance(bdict, dict) else bdict
    return [m for b in items for m in b.get("members", []) if m.get("ticker")]


def _membership_tickers(active_only: bool = False) -> list[str]:
    """Membership tickers. Default = every name that has ever been a member (the FETCH
    universe: a removed member's history still refreshes/repairs on disk).

    active_only=True drops names whose EVERY membership row carries a `removed` stamp —
    the curator's exit ledger. A ticker still live in ANY other basket stays active (12 of
    the 15 removed rows are cross-listed exits, e.g. HOOD crypto→fintech), so the filter is
    per-TICKER, never per-row. This is the set the staleness census judges: a name the
    curator has exited — or that the market has (a delisting) — must not read as a broken
    per-member pull forever.

    A member stamped `delisted_before_curation` is dropped from BOTH sets. The default
    universe is wide because a removed member's history is still worth repairing — but
    that reasoning assumes a history exists. These names have none: the security had
    already stopped existing when the curator wrote the row (silver_miners MAG and GATO,
    stamped 2026-08-07 against SEC Form 25-NSE receipts), so there is nothing on disk to
    refresh and nothing the vendor can ever return. Requesting them anyway is what
    config/delisted_symbols.yml exists to prevent: a symbol that can never resolve parks
    a permanent entry in the missing-symbol warning and trains the reader to ignore the
    one tripwire that would catch the NEXT real outage."""
    out: set[str] = set()
    active: set[str] = set()
    dead: set[str] = set()
    for m in _membership_rows():
        t = m["ticker"]
        out.add(t)
        if m.get("delisted_before_curation"):
            dead.add(t)
        if not m.get("removed"):
            active.add(t)
    return sorted((active if active_only else out) - dead)


def _removed_members() -> dict[str, dict]:
    """ticker -> {removed, rationale} for names removed from EVERY basket they sat in.
    Feeds the census's `inactive` disclosure so an exited/delisted member is explained in
    the freshness marker rather than silently dropped from the count."""
    active = {m["ticker"] for m in _membership_rows() if not m.get("removed")}
    out: dict[str, dict] = {}
    for m in _membership_rows():
        t = m["ticker"]
        if t in active:
            continue
        prev = out.get(t)
        rmv = str(m.get("removed") or "")
        if prev is None or rmv > prev["removed"]:      # last exit wins
            out[t] = {"removed": rmv, "rationale": str(m.get("rationale") or "")[:240]}
    return out


def _finviz_tickers(filters: list[str]) -> list[str]:
    """Every ticker in the given data/finviz_screener/<flt>.json classification files."""
    out: set[str] = set()
    base = config.data_dir() / "finviz_screener"
    for flt in filters:
        p = base / f"{flt}.json"
        if not p.exists():
            log.warning("finviz classification missing: %s", p)
            continue
        for r in (json.loads(p.read_text()).get("rows") or []):
            t = r.get("ticker")
            if t:
                out.add(t)
    return sorted(out)


def _store_tickers(odir: Path | None = None) -> list[str]:
    """Every ticker that already has a parquet in the deep store.

    This is the SELF-MAINTENANCE leg (--store): a file on disk is, by itself, a standing
    claim that something once wanted this tape. Honouring that claim is what stops an
    index reconstitution from silently orphaning a name — see the module docstring."""
    odir = odir or (config.data_dir() / "baskets" / "ohlcv")
    if not odir.is_dir():
        return []
    return sorted(p.stem for p in odir.glob("*.parquet"))


def _resolve_universe(explicit: list[str], fv: list[str], with_members: bool,
                      with_store: bool = False) -> list[str]:
    """The tickers a run maintains. Membership is the default universe; an explicit
    --tickers/--finviz set replaces it unless with_members unions it back in.
    with_store additionally unions every ticker already on disk.

    Resolved exits (config/delisted_symbols.yml) are subtracted from every DERIVED leg —
    membership, finviz and store — because a security that stopped existing can never
    return and requesting it nightly forever parks a permanent entry in the missing-symbol
    warning, training the reader to ignore the one tripwire that would catch the next real
    outage. An operator's EXPLICIT --tickers is never filtered: asking for a dead symbol by
    name is a deliberate backfill/debug act, not the nightly's standing request list."""
    derived: set[str] = set(fv)
    if with_store:
        derived |= set(_store_tickers())
    if with_members or not (derived or explicit):
        derived |= set(_membership_tickers())
    return sorted((derived - delisted_symbols.tickers()) | set(explicit))


# The finviz screener universes the NIGHTLY IS CONTRACTUALLY REQUIRED TO MAINTAIN, declared
# here rather than read back off the fetch call's arguments. That independence is the whole
# point (the #776 lesson): a census parameterised from the fetch's own argv goes blind at
# exactly the moment the fetch loses a universe, which is the failure it exists to catch.
# If collect.py stops passing these filters, the census keeps judging their names and the
# resulting laggards are reported — loudly — instead of quietly leaving the ruler.
MAINTAINED_FINVIZ_FILTERS: tuple[str, ...] = ("idx_ndx", "idx_rut")


def _sponsored_universe() -> tuple[set[str], list[str]]:
    """(tickers someone actively DECLARES should be tracked, filters that failed to resolve).

    Sponsorship = an active basket-membership row or a declared finviz index universe. It is
    deliberately NOT the same thing as "maintained": --store also maintains names no index or
    curator claims any more, and telling those two apart is what lets the census separate a
    BROKEN PULL (sponsored, lagging) from an ORPHAN (unsponsored, lagging) — the first is an
    outage, the second is a name awaiting re-sponsorship or an exit row."""
    unresolved: list[str] = []
    fv: set[str] = set()
    base = config.data_dir() / "finviz_screener"
    for flt in MAINTAINED_FINVIZ_FILTERS:
        got = _finviz_tickers([flt])
        if not got or not (base / f"{flt}.json").exists():
            unresolved.append(flt)
        fv |= set(got)
    return (set(_membership_tickers(active_only=True)) | fv) - delisted_symbols.tickers(), unresolved


# ------------------------------------------------------------------ staleness tripwire
STALE_SESSIONS = 3          # warn when a member's last row lags the store max by more

# Every store engine/basket_index falls through for a member's tape, in its preference
# order (engine/basket_index._member_ohlcv). A member absent from the DEEP store alone
# still renders — the fallbacks cover it, which is the graceful degradation this store
# was designed for. A member absent from ALL of these has no price series anywhere: its
# basket silently renders on N-1 members and every coverage receipt quietly rounds down.
# The two failures are reported separately below because only the second is data loss.
FALLBACK_RUNGS: tuple[tuple[str, ...], ...] = (
    ("baskets", "ohlcv"),   # this store — deep OHLCV, preferred
    ("stocks",),            # US stock library — already OHLCV
    ("china_stocks",),      # A-shares (.SS/.SZ tickers; never collides with the US stores)
    ("yahoo",),             # close+volume; high/low/open synthesised from the close
)


def _absent_from_all_rungs(tickers: list[str], data_dir: Path | None = None) -> list[str]:
    """Of `tickers`, those with no per-ticker parquet on ANY rung basket_index reads.

    Existence-only (no parse): a present-but-empty file is the deep store's own problem
    and is caught by the staleness census, whereas a name with no file anywhere can
    never resolve a tape no matter which fallback runs."""
    root = data_dir or config.data_dir()
    dark: list[str] = []
    for t in tickers:
        if not any((root.joinpath(*rung) / f"{t}.parquet").exists() for rung in FALLBACK_RUNGS):
            dark.append(t)
    return dark


def _last_row_date(p: Path) -> date | None:
    """Last-row date of a per-ticker parquet from the footer (last row group, date column
    only) — cheap enough to census the whole store nightly."""
    import pyarrow.parquet as pq
    pf = pq.ParquetFile(p)
    names = pf.schema_arrow.names
    dc = next((c for c in ("date", "Date", "timestamp", "__index_level_0__") if c in names), None)
    if dc is None:
        return None
    tbl = pf.read_row_group(pf.metadata.num_row_groups - 1, columns=[dc])
    v = tbl.column(0)[-1].as_py()
    return v.date() if isinstance(v, datetime) else (v if isinstance(v, date) else None)


def _sessions_behind(behind: date, ref: date) -> int:
    """NYSE sessions strictly after `behind`, up to and including `ref`."""
    from lib import nyse_calendar
    n, d = 0, behind + timedelta(days=1)
    while d <= ref:
        if nyse_calendar.is_session(d):
            n += 1
        d += timedelta(days=1)
    return n


def check_membership_staleness(odir: Path | None = None, members: list[str] | None = None,
                               threshold: int = STALE_SESSIONS, ops_alert: bool = True) -> dict:
    """Per-member freshness tripwire over the deep OHLCV store. WARN-ONLY — never raises,
    never blocks. Compares every active basket member's last-row date to the store-wide
    max and flags any lag > threshold sessions, plus members with no file at all.

    Exists because the whole-store check (build_baskets._check_basket_store_staleness,
    M7C-R8) is blind to a frozen SUBSET: 2026-07-16, #776 dropped the membership universe
    from the nightly pull and 528 member files froze for 11 sessions while the aggregate
    as_of stayed fresh — basket candles silently rendered from partial membership.

    ACTIVE means `removed` is unset on at least one membership row (see
    _membership_tickers): a name the curator has exited, or that the market has, is not a
    broken pull. Such a name is not counted stale — but if its tape has ALSO stopped it is
    named in `inactive` with its last bar and exit stamp, so the marker EXPLAINS it instead
    of going quietly green (BLD/TopBuild: acquired by QXO, NYSE-suspended 2026-07-01, no
    successor symbol — it read as a 22-session red line for a month).

    THE CENSUS JUDGES THE WHOLE STORE, NOT THE MEMBERSHIP SUBSET (2026-08-20). It used to
    ask only the 702 active members, so on a store of 2,782 files holding 183 stale ones it
    reported `n_stale: 1` — and that blindness is exactly why 179 orphaned files reached
    production. Every file now lands in one of three dispositions, and the three are kept
    apart because their CURES are different:

      * `stale`     — SPONSORED (an active membership row or a declared index universe,
                      `_sponsored_universe`) and lagging. Nothing should be able to sponsor
                      a name and not fetch it, so this is a BROKEN PULL: an outage. Alarm.
      * `unsponsored` — on disk, lagging, and claimed by no membership row and no declared
                      index universe. Not an outage — a name an index dropped. --store keeps
                      fetching it, so a live tape self-heals within one nightly; what remains
                      here after that is a tape that has genuinely STOPPED and needs a
                      resolved exit row (or re-sponsorship). A drainable work queue, reported
                      under its own annotation so it never dilutes the outage alarm.
      * `retired`   — a resolved exit row in config/delisted_symbols.yml. The security stopped
                      existing; its last bar is a FACT, not a defect. Disclosed with its
                      receipt and excluded from every alarm, at ANY lag. AVB (AvalonBay,
                      acquired 2026-08-17) had a well-formed exit row on 2026-08-20 while
                      still sitting one session behind the store max — nothing read the
                      ledger, so it was days away from becoming BLD's permanent red line for
                      the second time.

    Writes data/quality/basket_ohlcv_freshness.json and returns the payload."""
    payload: dict = {"status": "error", "checked_at": datetime.now(timezone.utc).isoformat(),
                     "threshold_sessions": threshold}
    try:
        odir = odir or (config.data_dir() / "baskets" / "ohlcv")
        explicit_members = members is not None
        members = _membership_tickers(active_only=True) if members is None else members
        last: dict[str, date] = {}
        for p in odir.glob("*.parquet"):
            try:
                d = _last_row_date(p)
                if d is not None:
                    last[p.stem] = d
            except Exception as e:  # noqa: BLE001 — one bad file must not kill the census
                log.warning("staleness census: unreadable %s: %s", p.name, e)
        if not last:
            payload["status"] = "no_store"
            _write_freshness_marker(payload)
            return payload
        store_max = max(last.values())
        dead = delisted_symbols.tickers()
        # The alarm ruler is the SPONSORED universe (active membership + the declared index
        # universes), not membership alone — a broken pull on an NDX/Russell name was
        # invisible to this census for as long as it existed. `members` stays the ruler for
        # `missing`/`absent_all_rungs` below, whose subject is basket COVERAGE (a basket
        # rendering on N-1 members), which an index name cannot affect.
        if explicit_members:
            sponsored, finviz_unresolved = set(members) - dead, []
        else:
            sponsored, finviz_unresolved = _sponsored_universe()
        stale: dict[str, dict] = {}
        behind_ok = 0
        missing = sorted(t for t in members if t not in last and t not in dead)
        for t in sponsored:
            d = last.get(t)
            if d is None or d >= store_max:
                continue
            lag = _sessions_behind(d, store_max)
            if lag > threshold:
                stale[t] = {"last": d.isoformat(), "sessions_behind": lag}
            elif lag > 0:
                behind_ok += 1
        stale = dict(sorted(stale.items(), key=lambda kv: -kv[1]["sessions_behind"]))

        # --- the store plane: every file, including the ones nothing sponsors any more ---
        # A resolved exit is disclosed at ANY lag (its last bar is a fact, not a defect) and
        # never reaches an alarm bucket. Everything else on disk that no one sponsors is an
        # ORPHAN: --store keeps fetching it, so a live tape self-heals by the next nightly
        # and only a genuinely stopped one persists here.
        retired: dict[str, dict] = {}
        for t in sorted(dead & set(last)):
            row = delisted_symbols.disclosure(t) or {}
            d = last[t]
            retired[t] = {"last": d.isoformat(),
                          "sessions_behind": _sessions_behind(d, store_max) if d < store_max else 0,
                          # `last_session` is the TRUE tape end; `last` is the store tip, and
                          # the two differ whenever the vendor flat-forwards a dead symbol
                          # (AVB's store tip 2026-08-19 is a 0-volume repeat carried four
                          # sessions past its real 2026-08-14 close). Reporting both is what
                          # lets a reader see padding rather than trust it as trading.
                          "last_session": row.get("last_session"),
                          "delisted_on": row.get("on"),
                          "reason": row.get("reason"),
                          # null = nothing continues this price series (ledger header)
                          "successor_ticker": row.get("successor_ticker")}
        unsponsored: dict[str, dict] = {}
        unsponsored_fresh = 0
        for t in sorted(set(last) - sponsored - dead):
            d = last[t]
            if d >= store_max:
                unsponsored_fresh += 1
                continue
            lag = _sessions_behind(d, store_max)
            if lag > threshold:
                unsponsored[t] = {"last": d.isoformat(), "sessions_behind": lag}
            else:
                unsponsored_fresh += 1
        unsponsored = dict(sorted(unsponsored.items(), key=lambda kv: -kv[1]["sessions_behind"]))
        # Disclosure, not silence: an inactive member whose tape has ALSO stopped is named
        # here with its last real bar and exit stamp. Excluded from n_stale (it is not a
        # broken pull) but never invisible — a delisting must be readable in the marker.
        inactive: dict[str, dict] = {}
        for t, rec in ({} if explicit_members else _removed_members()).items():
            d = last.get(t)
            if d is None or d >= store_max or t in dead:   # a resolved exit is `retired`
                continue
            lag = _sessions_behind(d, store_max)
            if lag > threshold:
                inactive[t] = {"last": d.isoformat(), "sessions_behind": lag, **rec}
        # Of the members this store lacks, which have no tape on ANY rung — the
        # fallbacks cover the rest, so only these are actual coverage loss.
        dark = _absent_from_all_rungs(missing, odir.parent.parent)
        payload.update({
            # `status` stays bound to the SPONSORED plane. Orphans deliberately do not turn
            # it red: the genuinely-stopped tail of them can only be cleared by curating exit
            # rows, and a top-line status that stays red until someone does is a status
            # nobody reads — the same warning-fatigue argument config/delisted_symbols.yml
            # makes about never requesting a dead symbol forever. They get their own
            # annotation and their own counts instead.
            "status": "stale" if (stale or missing) else "ok",
            "store_max": store_max.isoformat(), "n_members": len(members),
            "n_stale": len(stale), "n_behind_within_threshold": behind_ok,
            "stale": stale,
            "missing": missing,
            "inactive": dict(sorted(inactive.items(), key=lambda kv: -kv[1]["sessions_behind"])),
            "absent_all_rungs": dark,
            "n_absent_all_rungs": len(dark),
            # --- store plane (2026-08-20): the whole store, not the membership subset ---
            "n_store_files": len(last),
            "n_sponsored": len(sponsored),
            "n_sponsored_no_file": len(sponsored - set(last)),
            "unsponsored": unsponsored,
            "n_unsponsored_stale": len(unsponsored),
            "n_unsponsored_fresh": unsponsored_fresh,
            "retired": retired,
            "n_retired": len(retired),
            # A declared universe that resolves to NOTHING is itself the outage: every name
            # it sponsors silently becomes an orphan. Named so the marker distinguishes
            # "the index dropped 110 names" from "the screener pull failed".
            "maintained_finviz_filters": list(MAINTAINED_FINVIZ_FILTERS),
            "finviz_unresolved": finviz_unresolved,
        })
        if finviz_unresolved:
            fmsg = (f"declared finviz universe(s) resolved to nothing: "
                    f"{', '.join(finviz_unresolved)} — every name they sponsor now reads as "
                    f"UNSPONSORED, so a failed screener pull is masquerading as an index "
                    f"reconstitution. Check data/finviz_screener/<filter>.json")
            print(f"::warning title=basket-ohlcv-finviz-unresolved::{fmsg}", flush=True)
            log.warning(fmsg)
        if unsponsored:
            worst_u = max(unsponsored.items(), key=lambda kv: kv[1]["sessions_behind"])
            umsg = (f"basket OHLCV store: {len(unsponsored)} file(s) are stale AND sponsored by "
                    f"no active membership row or declared index universe "
                    f"({', '.join(MAINTAINED_FINVIZ_FILTERS)}) — worst {worst_u[0]} @ "
                    f"{worst_u[1]['last']}, {worst_u[1]['sessions_behind']} sessions behind: "
                    f"{', '.join(list(unsponsored)[:8])}. --store keeps fetching these, so a name "
                    "still trading self-heals on the next nightly; one that persists here has a "
                    "STOPPED tape and needs either re-sponsorship (a membership row / index "
                    "filter) or a resolved exit row in config/delisted_symbols.yml. Until then "
                    "engine/stage_analysis.build_universe() keeps classifying it, because that "
                    "function globs the store and never forgets a ticker. "
                    "See data/quality/basket_ohlcv_freshness.json")
            print(f"::warning title=basket-ohlcv-unsponsored-stale::{umsg}", flush=True)
            log.warning(umsg)
            if ops_alert:
                try:
                    from engine.alert_triage import push_ops_alert  # noqa: PLC0415
                    push_ops_alert(source="fetch_basket_ohlcv", type_="basket_ohlcv_unsponsored_stale",
                                   message=umsg, severity="minor", lane="collect", window_hours=20)
                except Exception as e:  # noqa: BLE001 — fail-open, the ::warning stands
                    log.debug("unsponsored census: push_ops_alert unavailable (%s)", e)
        if retired:
            log.info("staleness census: %d resolved exit(s) disclosed, excluded from every "
                     "alarm: %s", len(retired),
                     ", ".join(f"{t} (last {v['last']}, delisted {v['delisted_on']})"
                               for t, v in retired.items()))
        if inactive:
            log.info("staleness census: %d inactive member tape(s) stopped, disclosed not "
                     "flagged: %s", len(inactive),
                     ", ".join(f"{t} (last {v['last']}, removed {v['removed']})"
                               for t, v in inactive.items()))
        if dark:
            dmsg = (f"{len(dark)} basket member(s) have NO price series on any store rung "
                    f"({', '.join('/'.join(r) for r in FALLBACK_RUNGS)}): {', '.join(dark)} "
                    "— every basket holding one silently renders and grades on N-1 members, "
                    "and its coverage receipt rounds down with no other tell. Usual cause: a "
                    "ticker RENAME the vendor already followed (fetch 404s under the old "
                    "symbol) — add membership-ticker -> vendor-symbol to lib/ticker_aliases; "
                    "otherwise the name is off every feed and the basket membership is wrong. "
                    "See data/quality/basket_ohlcv_freshness.json")
            print(f"::warning title=basket-member-no-price-series::{dmsg}", flush=True)
            log.warning(dmsg)
            if ops_alert:
                try:
                    from engine.alert_triage import push_ops_alert  # noqa: PLC0415
                    push_ops_alert(source="fetch_basket_ohlcv", type_="basket_member_no_price_series",
                                   message=dmsg, severity="critical", lane="collect", window_hours=20)
                except Exception as e:  # noqa: BLE001 — fail-open, the ::warning stands
                    log.debug("all-rungs census: push_ops_alert unavailable (%s)", e)
        if stale or missing:
            worst = max(stale.items(), key=lambda kv: kv[1]["sessions_behind"]) if stale else None
            msg = (f"basket OHLCV store: {len(stale)} active members stale >{threshold} sessions "
                   f"vs store max {store_max}"
                   + (f" (worst {worst[0]} @ {worst[1]['last']}, {worst[1]['sessions_behind']} behind)" if worst else "")
                   + (f"; {len(missing)} members with no file in THIS store "
                      f"({len(missing) - len(dark)} covered by a fallback rung, {len(dark)} on no "
                      f"rung at all): {', '.join(missing[:8])}" if missing else "")
                   + " — the per-member pull is failing or the nightly call lost membership "
                     "coverage; see data/quality/basket_ohlcv_freshness.json")
            print(f"::warning ::{msg}", flush=True)
            log.warning(msg)
            if ops_alert:
                try:
                    from engine.alert_triage import push_ops_alert  # noqa: PLC0415
                    push_ops_alert(source="fetch_basket_ohlcv", type_="basket_member_ohlcv_stale",
                                   message=msg, severity="major", lane="collect", window_hours=20)
                except Exception as e:  # noqa: BLE001 — fail-open, the ::warning stands
                    log.debug("staleness census: push_ops_alert unavailable (%s)", e)
    except Exception as e:  # noqa: BLE001 — tripwire must never crash the collect lane
        log.warning("basket OHLCV staleness census failed: %s", e)
        payload["error"] = str(e)
    _write_freshness_marker(payload)
    return payload


def _write_freshness_marker(payload: dict) -> None:
    try:
        p = config.data_dir() / "quality" / "basket_ohlcv_freshness.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(payload, indent=2))
    except Exception as e:  # noqa: BLE001 — the marker is advisory, never the gate
        log.warning("freshness marker write failed: %s", e)


def _scrub_placeholder_prices(df: pd.DataFrame) -> pd.DataFrame:
    """Zero/negative "prices" are vendor placeholders, not trades (e.g. DEC shipped ~3y of
    all-zero OHLC rows with nonzero volume from before its US listing). Mask them to NaN —
    the same guard engine/basket_index applies at read time — and drop rows left with no
    price at all. Runs on the MERGED frame so a refresh purges prior garbage instead of
    re-persisting it via combine_first."""
    px = [c for c in ("open", "high", "low", "close") if c in df.columns]
    df[px] = df[px].where(df[px] > 0)
    return df[df[px].notna().any(axis=1)]


def _download_ohlcv(tickers: list[str]) -> dict[str, pd.DataFrame]:
    """Per-ticker OHLCV frames, deep from START. Reuses the breadth yfinance pattern
    (crumb/cookie auth that works headless), batched with retry+backoff. group_by=ticker
    so each name comes back as its own Open/High/Low/Close/Volume block."""
    import yfinance as yf
    out: dict[str, pd.DataFrame] = {}
    for i in range(0, len(tickers), BATCH):
        batch = tickers[i:i + BATCH]
        for attempt in range(RETRIES):
            try:
                df = yf.download(batch, start=START, auto_adjust=True, progress=False,
                                 group_by="ticker", threads=True)
                if df is None or df.empty:
                    raise RuntimeError("empty frame")
                # Single-ticker downloads come back flat (no ticker level) — normalise.
                if not isinstance(df.columns, pd.MultiIndex):
                    df.columns = pd.MultiIndex.from_product([[batch[0]], df.columns])
                for t in batch:
                    if t not in df.columns.get_level_values(0):
                        continue
                    sub = df[t][["Open", "High", "Low", "Close", "Volume"]].copy()
                    sub.columns = COLS
                    sub = sub.dropna(how="all")
                    if not sub.empty:
                        out[t] = sub.sort_index()
                break
            except Exception as e:  # noqa: BLE001
                wait = BACKOFF_S * (2 ** attempt)
                log.warning("batch %d/%d (%s…) attempt %d failed (%s); retry in %.0fs",
                            i // BATCH + 1, (len(tickers) - 1) // BATCH + 1, batch[0],
                            attempt + 1, e, wait)
                time.sleep(wait)
        else:
            log.error("batch starting %s failed after %d retries — leaving to prior store", batch[0], RETRIES)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="cap tickers (debug)")
    ap.add_argument("--tickers", default="", help="explicit comma-separated ticker list")
    ap.add_argument("--finviz", default="", help="comma-separated finviz_screener filters "
                                                 "(e.g. idx_ndx,idx_rut) to pull every member of")
    ap.add_argument("--members", action="store_true",
                    help="union the basket membership into an explicit --tickers/--finviz "
                         "universe (it is the default only when neither is given)")
    ap.add_argument("--store", action="store_true",
                    help="union every ticker already in data/baskets/ohlcv into the universe, "
                         "so a name an index reconstitution dropped keeps being maintained "
                         "instead of freezing on disk forever (resolved exits still excluded)")
    ap.add_argument("--census", action="store_true",
                    help="skip fetching; run only the store-wide staleness tripwire")
    args = ap.parse_args(argv)

    odir = config.data_dir() / "baskets" / "ohlcv"
    odir.mkdir(parents=True, exist_ok=True)

    if args.census:
        payload = check_membership_staleness(odir)
        log.info("staleness census: %s (store max %s, %s files, %s stale, %s missing, "
                 "%s unsponsored-stale, %s retired)",
                 payload.get("status"), payload.get("store_max"), payload.get("n_store_files"),
                 payload.get("n_stale"), len(payload.get("missing") or []),
                 payload.get("n_unsponsored_stale"), payload.get("n_retired"))
        return 0

    explicit = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    fv = _finviz_tickers([f.strip() for f in args.finviz.split(",") if f.strip()]) if args.finviz else []
    members = _resolve_universe(explicit, fv, args.members, args.store)
    if args.limit:
        members = members[:args.limit]
    if not members:
        log.info("no members to fetch (need data/baskets/membership.json or --tickers/--finviz)")
        return 0

    log.info("fetching deep OHLCV for %d members", len(members))
    fetch_syms = [ALIASES.get(t, t) for t in members]
    rev = {ALIASES.get(t, t): t for t in members}        # yahoo symbol -> membership ticker
    try:
        fresh = _download_ohlcv(fetch_syms)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("OHLCV fetch failed entirely, keeping prior store: %s", e)
        return 0

    wrote, kept, blank = 0, 0, []
    for t in members:
        sym = ALIASES.get(t, t)
        new = fresh.get(sym)
        out_p = odir / f"{t}.parquet"
        prior = pd.read_parquet(out_p) if out_p.exists() else None
        if new is None or new.empty:
            if prior is None:
                blank.append(t)
            else:
                kept += 1            # flaky pull — prior store stands
            continue
        new = new.rename_axis("Date")
        merged = new if prior is None else new.combine_first(prior)
        merged.index = pd.DatetimeIndex(merged.index)
        merged.index.name = "Date"
        merged = merged.sort_index()[COLS]
        merged = _scrub_placeholder_prices(merged)
        merged.to_parquet(out_p)
        wrote += 1
    if blank:
        log.warning("no data (and no prior) for %d: %s", len(blank), ", ".join(blank))
    log.info("basket OHLCV store: wrote/updated %d, kept-prior %d, missing %d -> %s",
             wrote, kept, len(blank), odir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
