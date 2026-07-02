"""Per-stock margin financing (个股融资融券) — the A-share positioning plane.

The whole-market margin balance is already the dashboard's "crowd meter"
(collectors/china_margin.py). This adds the PER-NAME cut: how much leveraged
financing (融资余额) is riding a single stock, and whether it is building or
unwinding. It is the closest free A-share analog to the US per-name positioning
panel (short interest + insider) — A-share leverage is retail-driven, so a fast
build-up in a name's financing balance is a crowding / froth tell, and an unwind
is de-risking.

  stock_margin_detail_sse(date)  / stock_margin_detail_szse(date)
      -> per-name 融资余额 (financing balance) for one trading date, all SSE / SZSE
         margin-eligible names. We pull the latest available date and one ~20 trading
         days earlier (trading calendar from the china index store) and difference them.

Stored under data/china_margin_detail/detail.parquet (latest financing balance + the
prior value + dates). The engine (engine/china_extras.margin_positioning) turns this
into a financing-balance trend and a financing-as-%-of-market-cap reading.

DISPLAY-ONLY context. Margin-eligibility itself is not universal and leverage is not a
validated timing signal — it is a crowding/positioning backdrop, never a buy/sell call.
"""
from __future__ import annotations

import argparse
import logging

import pandas as pd

from lib import config, store
from collectors import _drip
from collectors.china_analyst import to_ticker, _num

log = logging.getLogger("china_margin_detail")

OUT = config.data_dir() / "china_margin_detail" / "detail.parquet"
LOOKBACK_TD = 20          # trading days for the financing-balance change window


def _trading_dates(n: int = 40) -> list[str]:
    """The last `n` A-share trading dates (YYYYMMDD), newest last, from the index store."""
    for sym in ("000001.SS", "510300.SS", "399001.SZ"):
        df = store.read("china", sym)
        if df is not None and len(df):
            return [d.strftime("%Y%m%d") for d in df.index[-n:]]
    return []


def _detail_for(date: str) -> dict[str, float]:
    """{ticker: 融资余额} across both exchanges for one date. Empty on failure."""
    import akshare as ak
    out: dict[str, float] = {}
    for fn in (ak.stock_margin_detail_sse, ak.stock_margin_detail_szse):
        try:
            df = fn(date=date)
        except Exception as e:  # noqa: BLE001
            log.debug("margin detail %s %s failed: %s", fn.__name__, date, e)
            continue
        if df is None or df.empty:
            continue
        cols = list(df.columns)
        code_col = next((c for c in cols if "代码" in str(c)), None)
        fin_col = "融资余额" if "融资余额" in cols else None
        if not code_col or not fin_col:
            continue
        for _, r in df.iterrows():
            t = to_ticker(r.get(code_col))
            fb = _num(r.get(fin_col))
            if t and fb is not None:
                out[t] = fb
    return out


def _first_populated(dates: list[str]) -> tuple[str, dict] | tuple[None, None]:
    """Walk newest→older, return the first date whose margin detail is non-empty."""
    for d in reversed(dates):
        m = _detail_for(d)
        if m:
            return d, m
    return None, None


def _stored_sessions() -> set[str]:
    """Financing-balance session `date`s already on disk (append-only PIT history)."""
    if not OUT.exists():
        return set()
    try:
        return set(pd.read_parquet(OUT, columns=["date"])["date"].astype(str).unique())
    except Exception:  # noqa: BLE001
        return set()


def refresh() -> int:
    """Latest financing balance per name + its value ~20 trading days earlier, APPENDED to the
    point-in-time history (keep-last per session `date`). Best-effort; returns names in the latest
    session (0 on failure / already-stored). Idempotent within a UTC day."""
    asof_today = pd.Timestamp.utcnow().strftime("%Y-%m-%d")
    if OUT.exists():
        try:
            if str(pd.read_parquet(OUT, columns=["asof"])["asof"].max()) >= asof_today:
                log.info("china margin detail: cache already fresh (%s)", asof_today)
                return 0
        except Exception:  # noqa: BLE001
            pass
    dates = _trading_dates(40)
    if len(dates) < LOOKBACK_TD + 1:
        log.warning("china margin detail: not enough trading dates (%d)", len(dates))
        return 0
    cur_date, cur = _first_populated(dates[-3:])     # today may not be published yet
    if not cur:
        log.warning("china margin detail: no recent date populated")
        return 0
    # prior target = LOOKBACK_TD trading days before the populated current date
    try:
        ci = dates.index(cur_date)
    except ValueError:
        ci = len(dates) - 1
    prior_slice = dates[max(0, ci - LOOKBACK_TD - 2): ci - LOOKBACK_TD + 1] or dates[:1]
    prior_date, prior = _first_populated(prior_slice)
    prior = prior or {}
    cur_iso = pd.to_datetime(cur_date).strftime("%Y-%m-%d")
    if cur_iso in _stored_sessions():                     # append-only idempotency = per SESSION
        log.info("china margin detail: session %s already stored", cur_iso)
        return 0
    rows = []
    asof = asof_today
    for t, fb in cur.items():
        rows.append({"ticker": t, "fin_balance": fb,
                     "fin_balance_prior": prior.get(t),
                     "date": cur_iso,
                     "prior_date": (pd.to_datetime(prior_date).strftime("%Y-%m-%d")
                                    if prior_date else None),
                     "asof": asof})
    if not rows:
        return 0
    n = _drip.append_snapshot(OUT, rows, date_col="date")
    log.info("china margin detail: appended %s (%d names, %s vs %s)",
             OUT, n, cur_date, prior_date)
    return n


def backfill(start: str, end: str) -> int:
    """Range-backfill per-name financing-balance PIT history for [start, end] (YYYY-MM-DD). akshare's
    stock_margin_detail_{sse,szse}(date) serves per-date history. Appends each populated session
    (keep-last per session `date`); skips sessions already stored. Returns NEW sessions appended.
    (No prior-diff on backfilled rows — fin_balance_prior is left None; the PIT level is the record.)"""
    asof = pd.Timestamp.utcnow().strftime("%Y-%m-%d")
    have = _stored_sessions()
    added = 0
    for d in pd.bdate_range(start, end):
        iso = d.strftime("%Y-%m-%d")
        if iso in have:
            continue
        m = _detail_for(d.strftime("%Y%m%d"))
        if not m:
            continue
        rows = [{"ticker": t, "fin_balance": fb, "fin_balance_prior": None,
                 "date": iso, "prior_date": None, "asof": asof} for t, fb in m.items()]
        _drip.append_snapshot(OUT, rows, date_col="date")
        added += 1
        log.info("china margin detail backfill: session %s (%d names)", iso, len(rows))
    log.info("china margin detail backfill: %d new sessions [%s..%s]", added, start, end)
    return added


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", nargs=2, metavar=("START", "END"),
                    help="range-backfill per-name financing-balance PIT history [START END]")
    a = ap.parse_args()
    if a.backfill:
        return 0 if backfill(a.backfill[0], a.backfill[1]) else 0
    return 0 if refresh() else 1


if __name__ == "__main__":
    raise SystemExit(main())
