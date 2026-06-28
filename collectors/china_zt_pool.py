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


def refresh() -> int:
    """Bake the most recent populated limit-up pool. Best-effort; returns names
    written (0 on failure). Idempotent within a UTC day: a cache already stamped
    with today's date is left untouched."""
    asof = pd.Timestamp.utcnow().strftime("%Y-%m-%d")
    if OUT.exists():
        try:
            if str(pd.read_parquet(OUT, columns=["asof"])["asof"].max()) >= asof:
                log.info("china zt pool: cache already fresh (%s)", asof)
                return 0
        except Exception:  # noqa: BLE001
            pass
    today = _dt.date.today()
    dates = [(today - _dt.timedelta(days=i)).strftime("%Y%m%d")
             for i in range(WALK_BACK_DAYS + 1)]
    pop_date, df = _first_populated(dates)
    if df is None:
        log.warning("china zt pool: no populated session in last %d days", WALK_BACK_DAYS)
        return 0
    rows = _parse(pop_date, df, asof)
    if not rows:
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(OUT, index=False)
    log.info("china zt pool: wrote %s (%d names, session %s, asof %s)",
             OUT, len(rows), pop_date, asof)
    return len(rows)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    argparse.ArgumentParser().parse_args()
    return 0 if refresh() else 1


if __name__ == "__main__":
    raise SystemExit(main())
