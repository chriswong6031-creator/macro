"""Limit-up pool (涨停板) — the A-share momentum / retail-froth plane.

Eastmoney publishes a per-name 涨停板 (daily-limit-up) pool: every name that hit
its +10%/+20% price ceiling on a given trading date, with how many consecutive
boards it has strung together (连板数), how much capital sealed the board (封板资金),
how many times the seal broke during the session (炸板次数), the day's turnover
(换手率) and the listed sector (所属行业).

  stock_zt_pool_em(date=YYYYMMDD) -> the whole limit-up pool for one trading date.

We walk back from today over OUR OWN session calendar to the most recent trading date and
bake a flat per-name snapshot under data/china_zt_pool/pool.parquet, refreshed each run.

`date` IS THE TRADE DATE, NEVER THE RUN DATE (2026-08-08 heal)
---------------------------------------------------------------
The endpoint does not 404 on a non-session date: asked for any date at or after the last
PUBLISHED session it CLAMPS and serves that session's pool.  This collector used to walk
back from today over raw calendar days, stop at the first non-empty response, and stamp the
row `date` with the date it had ASKED for — so every weekend run relabelled Friday's pool as
Saturday/Sunday.  Measured before the heal: 11 of 47 stored dates were non-sessions, and
each one was byte-identical to the session before it (2026-07-04/05 ≡ 07-03, …, 08-08 ≡
08-07).  Two defences now stand:
  1. the requested date is resolved against a session calendar derived from our own
     data/china_stocks_raw store BEFORE the fetch, so only real sessions are ever asked for
     or stamped (holidays included — no external calendar dependency);
  2. a payload fingerprint refuses to stamp a session with a pool already stored under a
     DIFFERENT date, which catches the same clamp on a real session the vendor has not
     published yet.
`asof` is the UTC day the row was scraped — provenance, not the market date; a stored
session whose `asof` is far past its `date` was recovered late, not observed late.

DISPLAY-ONLY context. A limit-up pool is the loudest LAGGING retail-momentum read
there is — 连板 leaders (龙头) and consecutive-board chains are a froth / crowding
tell, never a validated buy ranking. Consumed downstream by engine/china_extras
(zt_pool / zt_sector_breadth) for momentum tiers + sector breadth.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import logging

import pandas as pd

from lib import config
from collectors import _drip
from collectors.china_analyst import to_ticker, _num

log = logging.getLogger("china_zt_pool")

OUT = config.data_dir() / "china_zt_pool" / "pool.parquet"
WALK_BACK_DAYS = 10        # calendar days to walk back looking for a populated session
SESSION_SAMPLE_NAMES = 24  # raw-store names sampled to derive the CN session calendar
MAX_SESSIONS_PER_RUN = 4   # newest session + up to 3 recent gap fills, per run

# The fields that make one session's pool that session's: an identical set across two dates
# is a vendor re-serve, not two markets that happened to close the same way.
_FINGERPRINT_COLS = ("ticker", "consec_boards", "seal_fund_yi", "failed_seals", "turnover_pct")


def _col(cols: list[str], *needles: str) -> str | None:
    """First column whose name CONTAINS any needle (akshare names drift by version)."""
    for c in cols:
        s = str(c)
        if any(n in s for n in needles):
            return c
    return None


def _pool_for(date: str) -> pd.DataFrame | None:
    """The raw limit-up pool for one YYYYMMDD date. None on failure / empty."""
    import akshare as ak
    try:
        df = ak.stock_zt_pool_em(date=date)
    except Exception as e:  # noqa: BLE001 — one broken scrape must never break the build
        log.debug("china zt pool: %s failed (%s)", date, e)
        return None
    return df if df is not None and not df.empty else None


def session_calendar() -> frozenset[str]:
    """The CN trading sessions, read from OUR OWN price store — no external calendar.

    A date is a session iff at least one sampled name in data/china_stocks_raw has a bar on
    it.  The sample is deterministic and wide (``SESSION_SAMPLE_NAMES`` names evenly strided
    across the sorted store), so no single suspension can hide a session, and the calendar
    costs ~24 small parquet reads rather than 1,800.  Empty when the store is missing —
    callers then fall back to a weekday test and say so in the log.
    """
    root = config.data_dir() / "china_stocks_raw"
    if not root.is_dir():
        return frozenset()
    files = sorted(root.glob("*.parquet"))
    if not files:
        return frozenset()
    step = max(1, len(files) // SESSION_SAMPLE_NAMES)
    days: set[str] = set()
    for fp in files[::step][:SESSION_SAMPLE_NAMES]:
        try:
            idx = pd.read_parquet(fp, columns=["close"]).index
        except Exception:  # noqa: BLE001 — one unreadable name must not blind the calendar
            continue
        days.update(pd.to_datetime(idx).strftime("%Y-%m-%d"))
    return frozenset(days)


def candidate_sessions(anchor: _dt.date, sessions: frozenset[str]) -> list[str]:
    """Trade dates worth asking the vendor for, newest first (ISO ``YYYY-MM-DD``).

    Only real sessions are returned, so the clamped response for a weekend or holiday can
    never be stamped with the date it was asked for.  Without a calendar this degrades to a
    weekday filter, which stops the weekend defect but cannot see holidays.
    """
    window = [anchor - _dt.timedelta(days=i) for i in range(WALK_BACK_DAYS + 1)]
    if sessions:
        return [d.isoformat() for d in window if d.isoformat() in sessions]
    log.warning("china zt pool: no session calendar under data/china_stocks_raw — falling "
                "back to a weekday test (a holiday run can still mislabel)")
    return [d.isoformat() for d in window if d.weekday() < 5]


def _fingerprint(rows: list[dict]) -> str:
    """A stable digest of one session's pool, over the fields that identify the session."""
    body = sorted(tuple(str(r.get(c)) for c in _FINGERPRINT_COLS) for r in rows)
    return hashlib.sha1("\n".join("\x1f".join(t) for t in body).encode()).hexdigest()


def _stored_fingerprints() -> dict[str, str]:
    """{fingerprint: date} for every session already on disk."""
    if not OUT.exists():
        return {}
    try:
        df = pd.read_parquet(OUT)
    except Exception:  # noqa: BLE001
        return {}
    if df.empty or "date" not in df.columns:
        return {}
    cols = [c for c in _FINGERPRINT_COLS if c in df.columns]
    out: dict[str, str] = {}
    for d, part in df.groupby(df["date"].astype(str)):
        out[_fingerprint(part[cols].to_dict("records"))] = str(d)
    return out


def _parse(date: str, df: pd.DataFrame, asof: str) -> list[dict]:
    """Flatten one day's pool into our schema rows (substring column matching)."""
    cols = list(df.columns)
    code_c = _col(cols, "代码")
    name_c = _col(cols, "名称")
    consec_c = _col(cols, "连板数", "连板")
    seal_c = _col(cols, "封板资金", "封单资金")
    fail_c = _col(cols, "炸板次数")
    turn_c = _col(cols, "换手率")
    sector_c = _col(cols, "所属行业", "行业")
    if not code_c:
        return []
    iso = pd.to_datetime(date).strftime("%Y-%m-%d")
    rows: list[dict] = []
    for _, r in df.iterrows():
        t = to_ticker(r.get(code_c))
        if not t:
            continue
        seal = _num(r.get(seal_c)) if seal_c else None
        rows.append({
            "ticker": t,
            "name": str(r.get(name_c) or "") if name_c else "",
            "consec_boards": int(_num(r.get(consec_c)) or 1) if consec_c else 1,
            # 封板资金 is in yuan; store as 亿 (1e8) for readability
            "seal_fund_yi": round(seal / 1e8, 4) if seal is not None else None,
            "failed_seals": int(_num(r.get(fail_c)) or 0) if fail_c else 0,
            "turnover_pct": _num(r.get(turn_c)) if turn_c else None,
            "sector": str(r.get(sector_c) or "") if sector_c else "",
            "date": iso,
            "asof": asof,
        })
    return rows


def _stored_sessions() -> set[str]:
    """The set of session `date`s already on disk (append-only PIT history)."""
    if not OUT.exists():
        return set()
    try:
        return set(pd.read_parquet(OUT, columns=["date"])["date"].astype(str).unique())
    except Exception:  # noqa: BLE001
        return set()


def _collect(iso: str, asof: str, prints: dict[str, str]) -> int:
    """Fetch + store ONE trading session. Returns rows written for that session (0 = skipped).

    The stored slice for a session is REPLACED wholesale (``replace_dates``): the pool is a
    complete set, so a name that left it between an early scrape and the final one must be
    retired, not stranded by a per-ticker keep-last merge.  Other dates are untouched, so the
    tape stays append-only across sessions.
    """
    df = _pool_for(iso.replace("-", ""))
    if df is None:
        return 0
    rows = _parse(iso.replace("-", ""), df, asof)
    if not rows:
        return 0
    fp = _fingerprint(rows)
    served = prints.get(fp)
    if served is not None and served != iso:
        # The vendor clamped to an already-stored session — it has not published `iso` yet.
        log.warning("china zt pool: %s served the pool already stored for %s — not stamping "
                    "it as a second session", iso, served)
        return 0
    n = len(rows)
    _drip.append_snapshot(OUT, rows, date_col="date", replace_dates=True)
    prints[fp] = iso            # a gap-fill later in THIS run must see what we just stored
    log.info("china zt pool: stored session %s (%d names, asof %s)", iso, n, asof)
    return n


def refresh(anchor: _dt.date | None = None) -> int:
    """Bake the most recent trading sessions into the point-in-time history.

    The NEWEST session is always re-collected so a partial/intraday scrape is corrected by a
    later run of the same day (freshest wins, whole slice).  Older sessions are collected only
    when MISSING — which self-heals the gaps the old walk-back left behind whenever the vendor
    was late on the day itself (it stopped at the newest populated date, found it already
    stored, and skipped the session under it forever; 3 such gaps in this store).  Bounded by
    ``MAX_SESSIONS_PER_RUN`` and by ``WALK_BACK_DAYS``, so a run never costs more vendor calls
    than the old walk-back already did.

    ``anchor`` is the calendar day the walk-back starts from; it defaults to the UTC day, the
    same clock ``asof`` uses (China is UTC+8, so its trade date is never BEHIND the UTC date —
    anchoring there can never ask for a session that has not begun).  It is a parameter so the
    tests can pin the day without patching a global clock.

    Best-effort; returns rows written for the newest session collected (0 on failure)."""
    now = _dt.datetime.now(_dt.timezone.utc)
    asof = now.strftime("%Y-%m-%d")
    anchor = anchor or now.date()
    have = _stored_sessions()
    prints = _stored_fingerprints()
    cands = candidate_sessions(anchor, session_calendar())
    if not cands:
        log.warning("china zt pool: no trading session in the last %d days", WALK_BACK_DAYS)
        return 0

    first = 0
    written = 0
    for i, iso in enumerate(cands):
        if i and iso in have:                 # older sessions: collect only what is MISSING
            continue
        n = _collect(iso, asof, prints)
        if not n:
            continue
        first = first or n
        written += 1
        if written >= MAX_SESSIONS_PER_RUN:
            break
    if not written:
        log.warning("china zt pool: nothing stored from %d candidate session(s)", len(cands))
    return first


def backfill(start: str, end: str) -> int:
    """Range-backfill the limit-up pool PIT history: append every populated trading session in
    [start, end] (YYYY-MM-DD). akshare serves stock_zt_pool_em per-date, so history is fetchable.
    Skips sessions already stored. Returns the number of NEW sessions appended."""
    asof = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d")
    have = _stored_sessions()
    prints = _stored_fingerprints()
    sessions = session_calendar()
    days = pd.bdate_range(start, end)                      # weekdays; holidays return empty pools
    added = 0
    for d in days:
        iso = d.strftime("%Y-%m-%d")
        if iso in have:
            continue
        if sessions and iso not in sessions:               # a holiday inside the range
            continue
        if _collect(iso, asof, prints):
            added += 1
    log.info("china zt pool backfill: %d new sessions [%s..%s]", added, start, end)
    return added


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", nargs=2, metavar=("START", "END"),
                    help="range-backfill PIT history for [START END] (YYYY-MM-DD)")
    a = ap.parse_args()
    if a.backfill:
        return 0 if backfill(a.backfill[0], a.backfill[1]) else 0
    return 0 if refresh() else 1


if __name__ == "__main__":
    raise SystemExit(main())
