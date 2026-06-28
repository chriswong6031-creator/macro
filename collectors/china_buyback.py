"""Share-buyback program tracker for A-share names (keyless, via akshare/Eastmoney).

Buybacks (回购) are the cleanest A-share confirmer of issuer conviction: a board
committing real cash to retire shares, and — for SOE / 央企 names — the mechanical
seed of the 中特估 ("China Special Valuation") re-rating thesis (state-backed buyback
of a low-PB name). One WHOLE-MARKET Eastmoney call returns every announced program:

  stock_repurchase_em()  -> per name: 计划回购金额区间 (planned spend), 已回购金额
                            (amount executed so far), 占公告前一日总股本比例 (% of total
                            share capital), and 实施进度 (program status: 实施中/已完成/…).

Stored compactly under data/china_buyback/buyback.parquet
({ticker, name, plan_amt_yi, done_amt_yi, pct_shares, progress, asof}), refreshed
every build (one cheap call, no per-name loop). Amounts are converted to 亿 (/1e8).

CONFIRMER, NOT A STANDALONE SIGNAL. A buyback is corroborating evidence of value /
support, capped as a confirmer leg downstream (engine side), never a buy ranking on
its own — A-share single-factor edges are not validated (research/CHINA_HK_STOCK_SIGNALS.md).
"""
from __future__ import annotations

import argparse
import logging

import pandas as pd

from lib import config
from collectors.china_analyst import to_ticker, _num

log = logging.getLogger("china_buyback")

OUT = config.data_dir() / "china_buyback" / "buyback.parquet"


def _col(cols: list[str], *needles: str) -> str | None:
    """First column whose name contains ALL the given substrings (akshare names drift
    across versions, so we match by substring, never exact equality)."""
    for c in cols:
        s = str(c)
        if all(n in s for n in needles):
            return c
    return None


def fetch_table() -> pd.DataFrame | None:
    """The whole-market Eastmoney buyback table. Returns None on failure."""
    import akshare as ak
    try:
        df = ak.stock_repurchase_em()
    except Exception as e:  # noqa: BLE001 — one broken scrape must never break the build
        log.warning("china buyback: stock_repurchase_em failed (%s)", e)
        return None
    return df if df is not None and not df.empty else None


def refresh() -> int:
    """Fetch the whole-market buyback table once and bake a compact per-ticker row.
    Best-effort: returns the number of names written (0 on failure). Overwrites the
    cache each run (the source is a same-day snapshot, fully re-fetchable). Idempotent
    within a UTC day: a cache already stamped with today's date is left untouched."""
    today = pd.Timestamp.utcnow().strftime("%Y-%m-%d")
    if OUT.exists():
        try:
            if str(pd.read_parquet(OUT, columns=["asof"])["asof"].max()) >= today:
                log.info("china buyback: cache already fresh (%s)", today)
                return 0
        except Exception:  # noqa: BLE001
            pass
    df = fetch_table()
    if df is None:
        return 0
    cols = list(df.columns)
    code_col = _col(cols, "代码")
    name_col = _col(cols, "简称") or _col(cols, "名称")
    prog_col = _col(cols, "进度")
    # plan amount: prefer the upper bound of 计划回购金额区间, else any plan-amount col
    plan_col = _col(cols, "计划回购金额", "上限") or _col(cols, "计划回购金额")
    done_col = _col(cols, "已回购金额")
    # % of total share capital: prefer the upper bound of 占…总股本比例
    pct_col = _col(cols, "总股本比例", "上限") or _col(cols, "总股本比例")
    if not code_col:
        log.warning("china buyback: no code column in %s", cols)
        return 0
    rows = []
    for _, r in df.iterrows():
        t = to_ticker(r.get(code_col))
        if not t:
            continue
        plan = _num(r.get(plan_col)) if plan_col else None
        done = _num(r.get(done_col)) if done_col else None
        pct = _num(r.get(pct_col)) if pct_col else None
        rows.append({
            "ticker": t,
            "name": str(r.get(name_col) or "") if name_col else "",
            "plan_amt_yi": (plan / 1e8) if plan is not None else None,
            "done_amt_yi": (done / 1e8) if done is not None else None,
            "pct_shares": pct,
            "progress": str(r.get(prog_col) or "") if prog_col else "",
        })
    if not rows:
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out = pd.DataFrame(rows)
    out["asof"] = today
    out.to_parquet(OUT, index=False)
    log.info("china buyback: wrote %s (%d names, asof %s)", OUT, len(out), today)
    return len(out)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    argparse.ArgumentParser().parse_args()
    return 0 if refresh() else 1


if __name__ == "__main__":
    raise SystemExit(main())
