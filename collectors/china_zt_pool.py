"""Limit-up pool (涨停板) — the A-share momentum / retail-froth plane.

Eastmoney publishes a per-name 涨停板 (daily-limit-up) pool: every name that hit
its +10%/+20% price ceiling on a given trading date, with how many consecutive
boards it has strung together (连板数), how much capital sealed the board (封板资金),
how many times the seal broke during the session (炸板次数), the day's turnover
(换手率) and the listed sector (所属行业).

  stock_zt_pool_em(date=YYYYMMDD) -> the whole limit-up pool for one trading date.

We walk back from today to the most recent POPULATED trading date (weekends /
holidays / a not-yet-published session return empty) and bake a flat per-name
snapshot under data/china_zt_pool/pool.parquet, refreshed once per UTC day.

DISPLAY-ONLY context. A limit-up pool is the loudest LAGGING retail-momentum read
there is — 连板 leaders (龙头) and consecutive-board chains are a froth / crowding
tell, never a validated buy ranking. Consumed downstream by engine/china_extras
(zt_pool / zt_sector_breadth) for momentum tiers + sector breadth.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import logging

import pandas as pd

from lib import config
from collectors import _drip
from collectors.china_analyst import to_ticker, _num

log = logging.getLogger("china_zt_pool")

OUT = config.data_dir() / "china_zt_pool" / "pool.parquet"
WALK_BACK_DAYS = 10        # calendar days to walk back looking for a populated session


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


def _first_populated(dates: list[str]) -> tuple[str, pd.DataFrame] | tuple[None, None]:
    """Walk newest->older, return the first date with a non-empty pool."""
    for d in dates:
        df = _pool_for(d)
        if df is not None:
            return d, df
    return None, None


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


def refresh() -> int:
    """Bake the most recent populated limit-up pool and APPEND it to the point-in-time history
    (keep-last per session `date`, so a same-session re-collect corrects). Best-effort; returns
    names written for the latest session (0 on failure / already-stored session)."""
    asof = pd.Timestamp.utcnow().strftime("%Y-%m-%d")
    today = _dt.date.today()
    dates = [(today - _dt.timedelta(days=i)).strftime("%Y%m%d")
             for i in range(WALK_BACK_DAYS + 1)]
    pop_date, df = _first_populated(dates)
    if df is None:
        log.warning("china zt pool: no populated session in last %d days", WALK_BACK_DAYS)
        return 0
    iso = pd.to_datetime(pop_date).strftime("%Y-%m-%d")
    if iso in _stored_sessions():                          # append-only idempotency = per SESSION
        log.info("china zt pool: session %s already stored", iso)
        return 0
    rows = _parse(pop_date, df, asof)
    if not rows:
        return 0
    n = _drip.append_snapshot(OUT, rows, date_col="date")
    log.info("china zt pool: appended %s (%d names, session %s, asof %s)",
             OUT, n, pop_date, asof)
    return n


def backfill(start: str, end: str) -> int:
    """Range-backfill the limit-up pool PIT history: append every populated trading session in
    [start, end] (YYYY-MM-DD). akshare serves stock_zt_pool_em per-date, so history is fetchable.
    Skips sessions already stored. Returns the number of NEW sessions appended."""
    asof = pd.Timestamp.utcnow().strftime("%Y-%m-%d")
    have = _stored_sessions()
    days = pd.bdate_range(start, end)                      # weekdays; holidays return empty pools
    added = 0
    for d in days:
        iso = d.strftime("%Y-%m-%d")
        if iso in have:
            continue
        df = _pool_for(d.strftime("%Y%m%d"))
        if df is None:
            continue
        rows = _parse(d.strftime("%Y%m%d"), df, asof)
        if rows:
            _drip.append_snapshot(OUT, rows, date_col="date")
            added += 1
            log.info("china zt pool backfill: appended session %s (%d names)", iso, len(rows))
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
