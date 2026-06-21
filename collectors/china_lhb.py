"""龙虎榜 (Dragon-Tiger / abnormal-volume board) — the A-share smart-money tape.

When a name's intraday move or turnover breaches the exchange's abnormal-volume
thresholds it is published on the 龙虎榜 with the top buy/sell seats. Two whole-market
Eastmoney calls give the per-name picture over a trailing window:

  stock_lhb_detail_em(start_date, end_date)
      -> every board appearance: 龙虎榜净买额 (net buy, 元) + 上榜原因 (the trigger
         reason). This is the RETAIL/游资 hot-money tape — fast money chasing moves.
  stock_lhb_jgmmtj_em(start_date, end_date)
      -> the institutional-seat split per appearance: 买方/卖方机构数 (# institutional
         buy/sell seats) + 机构买入净额 (institutional net buy, 元). This is the cleaner
         LEADING smart-money leg — 机构吸筹 (institutional accumulation).

Aggregated per ticker over ~5 trading days into data/china_lhb/detail.parquet. 净额 are
reported in 元 and divided by 1e8 for the *_yi (亿) columns the engine reads. The engine
(engine/china_extras.lhb_inst) turns the institutional-seat split into an accumulation
score and flags 机构吸筹 (inst seats net-buying) vs 游资 (detail-only, no inst seats).

DISPLAY / CONTEXT, NOT A SCORED ALLOCATION SIGNAL. 龙虎榜 presence is a hot-money tell,
not a validated forward edge — surfaced as smart-money context alongside the validated
signals, never a buy ranking. Idempotent within a UTC day; degrades to 0 rows on any
akshare failure (never raises).
"""
from __future__ import annotations

import argparse
import json
import logging

import pandas as pd

from lib import config, store
from collectors.china_analyst import to_ticker, _num

log = logging.getLogger("china_lhb")

OUT = config.data_dir() / "china_lhb" / "detail.parquet"
WINDOW_TD = 5  # trailing trading-day window for the 龙虎榜 pull


def _col(cols, *needles):
    """First column whose name contains one of the substrings (akshare names drift)."""
    for c in cols:
        s = str(c)
        for n in needles:
            if n in s:
                return c
    return None


def _trading_window() -> tuple[str, str]:
    """(start, end) YYYYMMDD spanning the last WINDOW_TD A-share trading dates.

    Falls back to a ~9-calendar-day window if the index store is unavailable."""
    for sym in ("000001.SS", "510300.SS", "399001.SZ"):
        df = store.read("china", sym)
        if df is not None and len(df) > WINDOW_TD:
            dates = [d.strftime("%Y%m%d") for d in df.index[-WINDOW_TD:]]
            return dates[0], dates[-1]
    end = pd.Timestamp.utcnow().normalize()
    return (end - pd.Timedelta(days=9)).strftime("%Y%m%d"), end.strftime("%Y%m%d")


def _fetch_detail(start: str, end: str) -> pd.DataFrame | None:
    """The whole-market 龙虎榜 appearance tape. None on failure."""
    import akshare as ak
    try:
        df = ak.stock_lhb_detail_em(start_date=start, end_date=end)
    except Exception as e:  # noqa: BLE001 — one broken scrape must never break the build
        log.warning("china lhb: stock_lhb_detail_em failed (%s)", e)
        return None
    return df if df is not None and not df.empty else None


def _fetch_inst(start: str, end: str) -> pd.DataFrame | None:
    """The whole-market institutional-seat split. None on failure."""
    import akshare as ak
    try:
        df = ak.stock_lhb_jgmmtj_em(start_date=start, end_date=end)
    except Exception as e:  # noqa: BLE001
        log.warning("china lhb: stock_lhb_jgmmtj_em failed (%s)", e)
        return None
    return df if df is not None and not df.empty else None


def _agg_detail(df: pd.DataFrame) -> dict[str, dict]:
    """Per-ticker roll-up of the detail tape: net buy (亿), # appearances, reasons,
    last date."""
    cols = list(df.columns)
    c_code = _col(cols, "代码")
    c_name = _col(cols, "名称")
    c_net = _col(cols, "净买额", "净额")
    c_date = _col(cols, "上榜日")
    c_reason = _col(cols, "上榜原因", "原因")
    if not c_code or c_net is None:
        return {}
    out: dict[str, dict] = {}
    for _, r in df.iterrows():
        t = to_ticker(r.get(c_code))
        if not t:
            continue
        net = _num(r.get(c_net))
        rec = out.setdefault(t, {
            "name": str(r.get(c_name) or "") if c_name else "",
            "net_buy_yi": 0.0, "n_appearances": 0, "reasons": [], "last_date": None,
        })
        if net is not None:
            rec["net_buy_yi"] += net / 1e8
        rec["n_appearances"] += 1
        if c_reason:
            reason = str(r.get(c_reason) or "").strip()
            if reason and reason not in rec["reasons"]:
                rec["reasons"].append(reason)
        if c_date:
            d = r.get(c_date)
            try:
                d = pd.to_datetime(d).strftime("%Y-%m-%d")
            except Exception:  # noqa: BLE001
                d = None
            if d and (rec["last_date"] is None or d > rec["last_date"]):
                rec["last_date"] = d
    return out


def _agg_inst(df: pd.DataFrame) -> dict[str, dict]:
    """Per-ticker roll-up of the institutional-seat split: inst net buy (亿), summed
    buy/sell seat counts, last date."""
    cols = list(df.columns)
    c_code = _col(cols, "代码")
    c_net = _col(cols, "机构买入净额", "机构净买", "净额")
    c_nbuy = _col(cols, "买方机构数", "买方")
    c_nsell = _col(cols, "卖方机构数", "卖方")
    c_date = _col(cols, "上榜日")
    if not c_code or c_net is None:
        return {}
    out: dict[str, dict] = {}
    for _, r in df.iterrows():
        t = to_ticker(r.get(c_code))
        if not t:
            continue
        net = _num(r.get(c_net))
        nb = _num(r.get(c_nbuy)) if c_nbuy else None
        ns = _num(r.get(c_nsell)) if c_nsell else None
        rec = out.setdefault(t, {
            "inst_net_buy_yi": 0.0, "n_inst_buy": 0, "n_inst_sell": 0, "last_date": None,
        })
        if net is not None:
            rec["inst_net_buy_yi"] += net / 1e8
        if nb is not None:
            rec["n_inst_buy"] += int(nb)
        if ns is not None:
            rec["n_inst_sell"] += int(ns)
        if c_date:
            d = r.get(c_date)
            try:
                d = pd.to_datetime(d).strftime("%Y-%m-%d")
            except Exception:  # noqa: BLE001
                d = None
            if d and (rec["last_date"] is None or d > rec["last_date"]):
                rec["last_date"] = d
    return out


def refresh() -> int:
    """Pull the trailing-window 龙虎榜 detail + institutional-seat tables and bake a
    per-ticker parquet. Best-effort: returns names written (0 on failure). Idempotent
    within a UTC day (a cache already stamped with today's date is left untouched)."""
    today = pd.Timestamp.utcnow().strftime("%Y-%m-%d")
    if OUT.exists():
        try:
            if str(pd.read_parquet(OUT, columns=["asof"])["asof"].max()) >= today:
                log.info("china lhb: cache already fresh (%s)", today)
                return 0
        except Exception:  # noqa: BLE001
            pass
    start, end = _trading_window()
    detail = _fetch_detail(start, end)
    if detail is None:
        return 0
    det = _agg_detail(detail)
    inst_df = _fetch_inst(start, end)
    inst = _agg_inst(inst_df) if inst_df is not None else {}
    if not det:
        return 0
    rows = []
    for t, d in det.items():
        i = inst.get(t, {})
        last = max([x for x in (d.get("last_date"), i.get("last_date")) if x], default=None)
        rows.append({
            "ticker": t,
            "name": d.get("name") or "",
            "net_buy_yi": round(d.get("net_buy_yi", 0.0), 4),
            "n_appearances": int(d.get("n_appearances", 0)),
            "inst_net_buy_yi": round(i.get("inst_net_buy_yi", 0.0), 4),
            "n_inst_buy": int(i.get("n_inst_buy", 0)),
            "n_inst_sell": int(i.get("n_inst_sell", 0)),
            "reasons": json.dumps(d.get("reasons", []), ensure_ascii=False),
            "last_date": last,
            "asof": today,
        })
    if not rows:
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(OUT, index=False)
    log.info("china lhb: wrote %s (%d names, %s..%s)", OUT, len(rows), start, end)
    return len(rows)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    argparse.ArgumentParser().parse_args()
    return 0 if refresh() else 1


if __name__ == "__main__":
    raise SystemExit(main())
