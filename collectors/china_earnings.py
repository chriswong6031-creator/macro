"""A-share earnings-disclosure calendar (keyless, via akshare/Eastmoney).

The A-share parallel of the US Earnings panel (collectors/equity_earnings.py). Unlike
the US (point-in-time consensus + surprise history), the native A-share datum is the
DISCLOSURE schedule: every listed company pre-books (预约) a report date for each
fiscal period, then may revise it, then discloses. One WHOLE-MARKET call per period:

  stock_yysj_em(date="YYYYMMDD")  -> per name: 首次预约时间 (first booked date),
                                     一次/二次/三次变更日期 (revisions),
                                     实际披露时间 (actual disclosure, once filed).

Stored under data/china_earnings/calendar.parquet ({ticker, next_date, period, is_actual,
asof}). The engine (engine/china_extras.earnings_calendar) hands the page the soonest
upcoming disclosure date; the page computes the days-to-disclosure countdown client-side
(so the static JSON never goes stale) and shows a pre-disclosure caution in the entry bar.

DISPLAY-ONLY context — disclosure timing matters for the limit-up / event windows A-share
retail trade around, but it is a date, never a buy/sell signal.
"""
from __future__ import annotations

import argparse
import logging

import pandas as pd

from lib import config
from collectors.china_analyst import to_ticker

log = logging.getLogger("china_earnings")

OUT = config.data_dir() / "china_earnings" / "calendar.parquet"

# the scheduled-date columns in priority order (latest revision wins), then actual
_SCHED_COLS = ["三次变更日期", "二次变更日期", "一次变更日期", "首次预约时间"]
_ACTUAL_COL = "实际披露时间"


def _quarter_ends(n_back: int = 1, n_fwd: int = 1) -> list[str]:
    """YYYYMMDD strings for the quarter-ends spanning [today - n_back quarters,
    today + n_fwd quarters]. The next-to-be-reported period is what carries the
    upcoming 预约 dates, so we look slightly forward as well as back."""
    today = pd.Timestamp.now().normalize()
    base = pd.Timestamp(year=today.year, month=((today.quarter - 1) * 3 + 1), day=1)
    out = []
    for k in range(-n_back, n_fwd + 1):
        q = (base + pd.DateOffset(months=3 * k))
        # quarter-end = last day of that quarter
        qe = (q + pd.DateOffset(months=3)) - pd.Timedelta(days=1)
        out.append(qe.strftime("%Y%m%d"))
    return out


def _parse_date(v) -> pd.Timestamp | None:
    if v in (None, "", "--", "—") or (isinstance(v, float) and v != v):
        return None
    try:
        ts = pd.to_datetime(v, errors="coerce")
        return ts.normalize() if ts is not None and not pd.isna(ts) else None
    except Exception:  # noqa: BLE001
        return None


def _period_table(period: str) -> pd.DataFrame | None:
    import akshare as ak
    try:
        df = ak.stock_yysj_em(date=period)
    except Exception as e:  # noqa: BLE001
        log.debug("china earnings: yysj_em(%s) failed (%s)", period, e)
        return None
    return df if df is not None and not df.empty else None


def refresh(n_back: int = 2, n_fwd: int = 1) -> int:
    """Per name, the NEXT upcoming disclosure date (scheduled or actual, in the future)
    AND the MOST RECENT actual disclosure date, across the candidate reporting periods.
    A-share disclosure-booking opens only ~1 month before a period ends, so off-season
    (e.g. mid-June, between Q1 and H1) there is no upcoming date — the page then shows
    the last report as context. Returns names written (0 on failure). Bounded to a sane
    window so a stale far-past/future date is never surfaced. Idempotent within a UTC
    day (a cache already stamped today is left untouched)."""
    asof_today = pd.Timestamp.utcnow().strftime("%Y-%m-%d")
    if OUT.exists():
        try:
            if str(pd.read_parquet(OUT, columns=["asof"])["asof"].max()) >= asof_today:
                log.info("china earnings: cache already fresh (%s)", asof_today)
                return 0
        except Exception:  # noqa: BLE001
            pass
    today = pd.Timestamp.now().normalize()
    lo, hi = today - pd.Timedelta(days=200), today + pd.Timedelta(days=150)
    agg: dict[str, dict] = {}
    for period in _quarter_ends(n_back, n_fwd):
        df = _period_table(period)
        if df is None:
            continue
        cols = list(df.columns)
        sched = [c for c in _SCHED_COLS if c in cols]
        for _, r in df.iterrows():
            t = to_ticker(r.get("股票代码"))
            if not t:
                continue
            actual = _parse_date(r.get(_ACTUAL_COL)) if _ACTUAL_COL in cols else None
            booked = None
            for c in sched:                       # latest revision wins
                booked = _parse_date(r.get(c))
                if booked is not None:
                    break
            a = agg.setdefault(t, {"next": None, "next_period": None, "last": None})
            # next upcoming = soonest future scheduled/actual within window
            for d, is_actual in ((booked, False), (actual, True)):
                if d is None or not (lo <= d <= hi):
                    continue
                if d >= today and (a["next"] is None or d < a["next"]):
                    a["next"], a["next_period"] = d, period
                if is_actual and d <= today and (a["last"] is None or d > a["last"]):
                    a["last"] = d
    rows = []
    asof = asof_today
    for t, a in agg.items():
        if a["next"] is None and a["last"] is None:
            continue
        rows.append({"ticker": t,
                     "next_date": a["next"].strftime("%Y-%m-%d") if a["next"] is not None else None,
                     "last_date": a["last"].strftime("%Y-%m-%d") if a["last"] is not None else None,
                     "period": a["next_period"], "asof": asof})
    if not rows:
        log.warning("china earnings: no disclosure dates parsed")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(OUT, index=False)
    n_next = sum(1 for r in rows if r["next_date"])
    log.info("china earnings: wrote %s (%d names, %d with upcoming, asof %s)",
             OUT, len(rows), n_next, asof)
    return len(rows)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    argparse.ArgumentParser().parse_args()
    return 0 if refresh() else 1


if __name__ == "__main__":
    raise SystemExit(main())
