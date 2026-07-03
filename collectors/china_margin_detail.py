"""Per-stock margin financing (个股融资融券) — the A-share positioning plane.

The whole-market margin balance is already the dashboard's "crowd meter"
(collectors/china_margin.py). This adds the PER-NAME cut: how much leveraged
financing (融资余额) is riding a single stock, and whether it is building or
unwinding. It is the closest free A-share analog to the US per-name positioning
panel (short interest + insider) — A-share leverage is retail-driven, so a fast
build-up in a name's financing balance is a crowding / froth tell, and an unwind
is de-risking.

  stock_margin_detail_sse(date)  / stock_margin_detail_szse(date)
      -> per-name 融资余额 (financing balance) + 融券余量 (short-lending balance
         in shares) for one trading date, all SSE / SZSE margin-eligible names.
         We pull the latest available date and APPEND to the PIT history.

Schema (data/china_margin_detail/detail.parquet) — append-only, date-keyed:
  date           str  YYYY-MM-DD  trading date this row represents
  ticker         str  e.g. 600000.SS / 000001.SZ
  fin_balance    float  融资余额 (financing balance), raw yuan
  short_balance  float  融券余量 (short-lending volume, shares) — None where exchange
                        does not publish or call fails; SSE provides 融券余量 (shares),
                        SZSE provides 融券余额 (yuan) mapped to short_balance_yuan
  short_balance_yuan float  融券余额 (short-lending balance, yuan) — SZSE only; None on SSE
  fin_balance_prior   float  fin_balance ~20 trading days earlier (for velocity)
  prior_date     str  YYYY-MM-DD date of fin_balance_prior
  asof           str  YYYY-MM-DD UTC date this row was collected (collect-run stamp)

DISPLAY-ONLY context until the forward ledger matures (~60 accrued sessions needed
before per-name margin-velocity phase-0 is runnable). Margin-eligibility itself is
not universal and leverage is not a validated timing signal — it is a crowding/
positioning backdrop, never a buy/sell call.

ADAPTER REGISTRATION: ChinaMarginDetailAdapter is registered in scripts/collect.py
under the key ``china_margin_detail``. The ``china*`` prefix auto-assigns it to the
``asia`` group (asia-close.yml shard). Data written to data/china_margin_detail/ is
covered by ``git add data/`` in both daily.yml and asia-close.yml commit steps.
"""
from __future__ import annotations

import argparse
import logging

import pandas as pd

from collectors.base import Adapter
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


def _detail_for(date: str) -> dict[str, dict]:
    """{ticker: {fin_balance, short_balance, short_balance_yuan}} across both exchanges
    for one trading date. Uses {} on any exchange-level failure (best-effort)."""
    import akshare as ak
    out: dict[str, dict] = {}
    for exch, fn in (("sse", ak.stock_margin_detail_sse),
                     ("szse", ak.stock_margin_detail_szse)):
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
        # SSE column: 融券余量 (shares outstanding in margin lending)
        short_qty_col = "融券余量" if "融券余量" in cols else None
        # SZSE column: 融券余额 (yuan value of short lending)
        short_yuan_col = "融券余额" if "融券余额" in cols else None
        if not code_col or fin_col is None:
            continue
        for _, r in df.iterrows():
            t = to_ticker(r.get(code_col))
            fb = _num(r.get(fin_col))
            if t is None or fb is None:
                continue
            sb_qty = _num(r.get(short_qty_col)) if short_qty_col else None
            sb_yuan = _num(r.get(short_yuan_col)) if short_yuan_col else None
            if t in out:
                # merge: keep highest-confidence values (both exchanges may list same name)
                if sb_qty is not None:
                    out[t]["short_balance"] = sb_qty
                if sb_yuan is not None:
                    out[t]["short_balance_yuan"] = sb_yuan
            else:
                out[t] = {
                    "fin_balance": fb,
                    "short_balance": sb_qty,       # shares (SSE) or None
                    "short_balance_yuan": sb_yuan,  # yuan (SZSE) or None
                }
    return out


def _first_populated(dates: list[str]) -> tuple[str, dict] | tuple[None, None]:
    """Walk newest->older, return the first date whose margin detail is non-empty."""
    for d in reversed(dates):
        m = _detail_for(d)
        if m:
            return d, m
    return None, None


def _stored_sessions() -> set[str]:
    """Financing-balance session `date`s already on disk (append-only PIT history)."""
    path = config.data_dir() / "china_margin_detail" / "detail.parquet"
    if not path.exists():
        return set()
    try:
        return set(pd.read_parquet(path, columns=["date"])["date"].astype(str).unique())
    except Exception:  # noqa: BLE001
        return set()


def refresh() -> int:
    """Latest financing balance per name + its value ~20 trading days earlier, APPENDED to the
    point-in-time history (keep-last per session `date`). Best-effort; returns names in the latest
    session (0 on failure / already-stored). Idempotent within a UTC day."""
    out_path = config.data_dir() / "china_margin_detail" / "detail.parquet"
    asof_today = pd.Timestamp.utcnow().strftime("%Y-%m-%d")
    if out_path.exists():
        try:
            if str(pd.read_parquet(out_path, columns=["asof"])["asof"].max()) >= asof_today:
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
    for t, vals in cur.items():
        prior_vals = prior.get(t, {})
        rows.append({
            "date": cur_iso,
            "ticker": t,
            "fin_balance": vals["fin_balance"],
            "short_balance": vals.get("short_balance"),
            "short_balance_yuan": vals.get("short_balance_yuan"),
            "fin_balance_prior": prior_vals.get("fin_balance"),
            "prior_date": (pd.to_datetime(prior_date).strftime("%Y-%m-%d")
                           if prior_date else None),
            "asof": asof,
        })
    if not rows:
        return 0
    n = _drip.append_snapshot(out_path, rows, date_col="date")
    log.info("china margin detail: appended %s (%d names, %s vs %s)",
             out_path, n, cur_date, prior_date)
    return n


def backfill(start: str, end: str) -> int:
    """Range-backfill per-name financing-balance PIT history for [start, end] (YYYY-MM-DD). akshare's
    stock_margin_detail_{sse,szse}(date) serves per-date history. Appends each populated session
    (keep-last per session `date`); skips sessions already stored. Returns NEW sessions appended.
    (No prior-diff on backfilled rows — fin_balance_prior is left None; the PIT level is the record.)"""
    out_path = config.data_dir() / "china_margin_detail" / "detail.parquet"
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
        rows = [{
            "date": iso,
            "ticker": t,
            "fin_balance": vals["fin_balance"],
            "short_balance": vals.get("short_balance"),
            "short_balance_yuan": vals.get("short_balance_yuan"),
            "fin_balance_prior": None,
            "prior_date": None,
            "asof": asof,
        } for t, vals in m.items()]
        _drip.append_snapshot(out_path, rows, date_col="date")
        added += 1
        log.info("china margin detail backfill: session %s (%d names)", iso, len(rows))
    log.info("china margin detail backfill: %d new sessions [%s..%s]", added, start, end)
    return added


class ChinaMarginDetailAdapter(Adapter):
    """Wraps refresh() in the standard run_adapter / circuit-breaker machinery so
    china_margin_detail participates in the collect lane freshness / health tracking.
    Group ``china_margin_detail`` starts with ``china`` so it is auto-assigned to the
    ``asia`` shard (asia-close.yml). Data path data/china_margin_detail/ is covered by
    ``git add data/`` in that workflow's commit step.

    Adapter.fetch() is a no-op shim (stores are written via _drip.append_snapshot
    internally in refresh()); we return a sentinel DataFrame so run_adapter records
    a successful fetch. Actual failure is surfaced via the return-0 convention."""

    name = "china_margin_detail"
    group = "china_margin_detail"
    stale_after_days = 3   # trading daily; flag if 3 days stale (long weekend + 1)

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        n = refresh()
        # Return a one-row sentinel so run_adapter sees rows > 0 on success
        path = config.data_dir() / "china_margin_detail" / "detail.parquet"
        if n > 0 or not path.exists():
            sentinel = pd.DataFrame({"n_names": [n]}, index=[pd.Timestamp.utcnow().normalize()])
            return {"refresh": sentinel}
        # Already fresh — return the latest date slice as the sentinel
        try:
            df = pd.read_parquet(path, columns=["date", "ticker"])
            latest = _drip.latest_snapshot(df, "date")
            n_row = len(latest) if latest is not None else 0
            sentinel = pd.DataFrame({"n_names": [n_row]}, index=[pd.Timestamp.utcnow().normalize()])
            return {"refresh": sentinel}
        except Exception:  # noqa: BLE001
            sentinel = pd.DataFrame({"n_names": [0]}, index=[pd.Timestamp.utcnow().normalize()])
            return {"refresh": sentinel}


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
