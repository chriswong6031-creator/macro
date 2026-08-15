"""Block-trade (大宗交易) per-name conviction handoff — keyless, via akshare/Eastmoney.

Block trades are negotiated off-exchange transfers of large parcels. The PRICE the
block crosses at — relative to that day's close — is the tell:

  - a PREMIUM (溢价, 折溢率 > 0) means a buyer paid UP for size: a conviction handoff,
    someone wants the block badly enough to pay above market.
  - a DISCOUNT (折价, 折溢率 < 0) means a holder dumped size below market: institutional
    or insider unloading / de-risking.

  ak.stock_dzjy_mrtj(start_date, end_date)  -> the daily-statistics table (每日统计):
      one row per (name, trading-date) with 折溢率 (premium/discount), 成交总额 (block
      turnover, in 万元), 成交笔数 (number of blocks). We pull a trailing ~10 trading-day
      window and aggregate per name: turnover-weighted average premium, total 亿-turnover,
      block count, and the last date a block printed.

Stored under data/china_block_trades/detail.parquet
  ({ticker, name, avg_premium_pct, block_amt_yi, n_blocks, last_date, asof}),
refreshed at most once per UTC day. The engine (engine/china_extras.block_trades) turns
this into a signed block_score (premium = conviction, discount = unload).

EVIDENCE STORE (append-only, keep-first) — separate from the trailing-window snapshot:
  data/china_block_trades/events.parquet — one row per (ticker, event_date)
  Vendor event_date and first_seen are stored separately. A re-fetch of the same
  (ticker, event_date) cannot move first_seen or rewrite the first payload. The
  snapshot may roll forward; history does not.

UNIT NOTE (verified live against akshare): 折溢率 is a RATIO (fraction), NOT a percent —
e.g. close 52.61 / cross 48.93 ⇒ 折溢率 = -0.0699 = -7.0%. We multiply by 100 and store
`avg_premium_pct` in PERCENT. 成交总额 is in 万元; `block_amt_yi` = Σ成交总额 / 10000 (亿元).

DISPLAY-ONLY context. Block premium/discount is a positioning/conviction backdrop read
alongside the validated signals — never a standalone buy/sell ranking.
"""
from __future__ import annotations

import argparse
import logging
import time
from datetime import datetime, timezone

import pandas as pd

from lib import config, store
from collectors.china_analyst import to_ticker, _num
from collectors import _first_seen_store as fss

log = logging.getLogger("china_block_trades")

OUT = config.data_dir() / "china_block_trades" / "detail.parquet"
OUT_HIST = config.data_dir() / "china_block_trades" / "events.parquet"
WINDOW_TD = 10            # trailing trading-day window for block aggregation
SOURCE = "akshare.stock_dzjy_mrtj"

HIST_COLUMNS = (
    "ticker",
    "name",
    "event_date",
    "premium_pct",
    "block_amt_yi",
    "n_blocks",
    "first_seen",
    "fetched_at",
    "asof",
    "schema_version",
    "source",
)
HIST_KEY = ["ticker", "event_date"]


def _trading_dates(n: int = 20) -> list[str]:
    """The last `n` A-share trading dates (YYYYMMDD), newest last, from the index store."""
    for sym in ("000001.SS", "510300.SS", "399001.SZ"):
        df = store.read("china", sym)
        if df is not None and len(df):
            return [d.strftime("%Y%m%d") for d in df.index[-n:]]
    return []


def _fetch_window(start: str, end: str) -> pd.DataFrame | None:
    """One akshare call for the daily-statistics block table over [start, end]. None on failure."""
    import akshare as ak
    try:
        df = ak.stock_dzjy_mrtj(start_date=start, end_date=end)
    except Exception as e:  # noqa: BLE001 — one broken scrape must never break the build
        log.warning("china block trades: stock_dzjy_mrtj failed (%s)", e)
        return None
    return df if df is not None and not df.empty else None


def _col(cols: list[str], *needles: str):
    """First column whose name contains one of the substrings (akshare names drift)."""
    for c in cols:
        s = str(c)
        if any(nd in s for nd in needles):
            return c
    return None


def _normalize_event_date(value) -> str:
    """Vendor trade date → YYYY-MM-DD, or '' if unparseable. Never invents a date."""
    if value is None or (isinstance(value, float) and value != value):
        return ""
    s = str(value).strip()
    if not s or s in ("nan", "None", "NaT", "--", "—"):
        return ""
    try:
        return pd.to_datetime(s).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return ""


def _raw_event_iter(df: pd.DataFrame):
    """Yield parsed daily-statistics rows. Shared by snapshot roll-up and hist accrual."""
    cols = list(df.columns)
    code_col = _col(cols, "证券代码", "代码")
    name_col = _col(cols, "证券简称", "简称", "名称")
    prem_col = _col(cols, "折溢率")
    amt_col = _col(cols, "成交总额")  # NB: "成交总额/流通市值" also contains 成交总额 — order matters
    amt_candidates = [c for c in cols if "成交总额" in str(c)]
    if amt_candidates:
        amt_col = next((c for c in amt_candidates if "流通市值" not in str(c)), amt_candidates[0])
    date_col = _col(cols, "交易日期", "日期")
    n_col = _col(cols, "成交笔数", "笔数")
    if not code_col or prem_col is None:
        return
    for _, r in df.iterrows():
        t = to_ticker(r.get(code_col))
        if not t:
            continue
        prem = _num(r.get(prem_col))                       # RATIO (fraction)
        if prem is None:
            continue
        amt_wan = _num(r.get(amt_col)) if amt_col else None  # 万元
        amt_yi = (amt_wan / 1e4) if amt_wan is not None else 0.0  # 万元 -> 亿元
        n_blk = int(_num(r.get(n_col)) or 0) if n_col else 0
        event_date = _normalize_event_date(r.get(date_col) if date_col else None)
        yield {
            "ticker": t,
            "name": str(r.get(name_col) or "") if name_col else "",
            "event_date": event_date,
            "premium_ratio": prem,
            "block_amt_yi": amt_yi,
            "n_blocks": max(n_blk, 1),
        }


def event_rows_from_raw(df: pd.DataFrame, *, fetched_at: str, asof: str) -> list[dict]:
    """One evidence row per (ticker, event_date). Rows without a vendor date are dropped
    rather than stamped with an inferred date — first_seen is not a substitute event_date."""
    rows: list[dict] = []
    for ev in _raw_event_iter(df) or []:
        if not ev["event_date"]:
            continue
        rows.append({
            "ticker": ev["ticker"],
            "name": ev["name"],
            "event_date": ev["event_date"],
            "premium_pct": round(ev["premium_ratio"] * 100.0, 4),
            "block_amt_yi": round(ev["block_amt_yi"], 4),
            "n_blocks": int(ev["n_blocks"]),
            "first_seen": fetched_at,
            "fetched_at": fetched_at,
            "asof": asof,
            "schema_version": fss.SCHEMA_VERSION,
            "source": SOURCE,
        })
    return rows


def accrue_block_events(rows: list[dict]) -> int:
    """Append-only keep-first on (ticker, event_date). Returns net-new keys."""
    return fss.accrue_keep_first(
        OUT_HIST, rows, columns=HIST_COLUMNS, key=HIST_KEY,
        sort_by=["event_date", "ticker"],
    )


def _aggregate(df: pd.DataFrame) -> list[dict]:
    """Per-ticker roll-up over the window. 折溢率 (ratio) -> percent; 成交总额 (万元) -> 亿元."""
    acc: dict[str, dict] = {}
    for ev in _raw_event_iter(df) or []:
        t = ev["ticker"]
        a = acc.setdefault(t, {"name": ev["name"], "w_prem": 0.0, "w": 0.0,
                               "amt_yi": 0.0, "n_blocks": 0, "last_date": ""})
        w = ev["block_amt_yi"] if ev["block_amt_yi"] > 0 else 1.0
        a["w_prem"] += ev["premium_ratio"] * w
        a["w"] += w
        a["amt_yi"] += ev["block_amt_yi"]
        a["n_blocks"] += ev["n_blocks"]
        if ev["event_date"] and ev["event_date"] > a["last_date"]:
            a["last_date"] = ev["event_date"]
        if not a["name"] and ev["name"]:
            a["name"] = ev["name"]
    rows = []
    for t, a in acc.items():
        avg_prem = (a["w_prem"] / a["w"]) if a["w"] else 0.0
        rows.append({
            "ticker": t,
            "name": a["name"],
            "avg_premium_pct": round(avg_prem * 100.0, 4),   # ratio -> percent
            "block_amt_yi": round(a["amt_yi"], 4),
            "n_blocks": int(a["n_blocks"]),
            "last_date": a["last_date"] or None,
        })
    return rows


def refresh() -> int:
    """Aggregate the trailing ~10-trading-day block-trade window per name.
    Best-effort; returns names written (0 on failure). Idempotent within a UTC day."""
    asof = pd.Timestamp.utcnow().strftime("%Y-%m-%d")
    if OUT.exists():
        try:
            if str(pd.read_parquet(OUT, columns=["asof"])["asof"].max()) >= asof:
                log.info("china block trades: cache already fresh (%s)", asof)
                return 0
        except Exception:  # noqa: BLE001
            pass
    dates = _trading_dates(WINDOW_TD + 4)
    if dates:
        start, end = dates[0], dates[-1]
    else:  # store unavailable — fall back to a calendar window (~2 weeks)
        end_ts = pd.Timestamp.utcnow().normalize()
        start, end = (end_ts - pd.Timedelta(days=18)).strftime("%Y%m%d"), end_ts.strftime("%Y%m%d")
    time.sleep(1.0)  # throttle akshare
    df = _fetch_window(start, end)
    if df is None:
        return 0
    rows = _aggregate(df)
    if not rows:
        return 0
    fetched_at = datetime.now(timezone.utc).isoformat()
    n_hist = accrue_block_events(event_rows_from_raw(df, fetched_at=fetched_at, asof=asof))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out = pd.DataFrame(rows)
    out["asof"] = asof
    out.to_parquet(OUT, index=False)
    log.info("china block trades: wrote %s (%d names, %s..%s); hist +%d -> %s",
             OUT, len(out), start, end, n_hist, OUT_HIST)
    return len(out)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    argparse.ArgumentParser().parse_args()
    return 0 if refresh() else 1


if __name__ == "__main__":
    raise SystemExit(main())
