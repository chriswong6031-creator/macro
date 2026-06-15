"""Collect descriptive fundamentals for A-share names (keyless, via akshare).

The China parallel of the US fundamentals pipeline (collectors/edgar_facts.py +
engine/stock_fundamentals.py). akshare pulls, per name, from public Chinese
sources (THS / Eastmoney / cninfo) — no token, no account:

  - stock_zyjs_ths            -> company / main-business description
  - stock_financial_abstract  -> the heavy lifter: ~80 indicators across every
                                 report period (revenue, net profit, EPS, FCF/sh,
                                 ROE, ROA, margins, leverage, current ratio,
                                 asset turnover, growth) — one fast call carries
                                 BOTH the multi-year trend AND every Piotroski /
                                 Altman input, so no slow per-period statement
                                 fetch is needed.
  - stock_dividend_cninfo     -> dividend history (for a yield / payout read)
  - stock_zh_a_gdhs_detail_em -> shareholder-count trend (an A-share-specific
                                 retail-concentration tell)

Stored compact: ONE row per ticker in data/china_fundamentals/fundamentals.parquet
with a JSON `payload` of the raw-ish record; engine/china_fundamentals.py does the
derivation (trend series, Piotroski, Altman, valuation-vs-sector, archetype).

Resumable + widen-able: an existing cache is reused (names fresher than --max-age
days are skipped), so the nightly job can fetch a high-value SUBSET first and
widen toward the full universe over subsequent runs. Best-effort throughout —
one bad name never aborts the run.

Usage:
  python -m collectors.china_fundamentals            # the high-value subset
  python -m collectors.china_fundamentals --all       # the full search universe
  python -m collectors.china_fundamentals --tickers 600519.SS,000858.SZ
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("china_fundamentals")

OUT = config.data_dir() / "china_fundamentals" / "fundamentals.parquet"

# stock_financial_abstract '指标' (indicator) -> our compact field name. The same
# label can appear under several '选项' groups; we take the first seen (常用指标 wins).
_IND = {
    "营业总收入": "revenue",
    "归母净利润": "ni",
    "营业成本": "cost",
    "经营现金流量净额": "cfo",
    "基本每股收益": "eps",
    "每股净资产": "bvps",
    "每股企业自由现金流量": "fcf_ps",
    "净资产收益率(ROE)": "roe",
    "总资产报酬率(ROA)": "roa",
    "毛利率": "gross_margin",
    "销售净利率": "net_margin",
    "资产负债率": "debt_ratio",
    "股东权益合计(净资产)": "equity",
    "流动比率": "current_ratio",
    "权益乘数": "equity_multiplier",
    "总资产周转率": "asset_turnover",
    "每股留存收益": "retained_earnings_ps",
    "息税前利润率": "ebit_margin",
    "营业总收入增长率": "rev_growth",
    "归属母公司净利润增长率": "ni_growth",
}


def ak_symbol(ticker: str) -> str:
    """600519.SS / 000001.SZ -> 600519 / 000001 (akshare's bare 6-digit code)."""
    return ticker.split(".")[0]


def _num(v):
    try:
        if v in (None, "", "--", "—"):
            return None
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def _abstract_rows(ak, sym: str) -> list[dict]:
    """Parse stock_financial_abstract into per-fiscal-year rows (year-end only),
    newest last, last ~7 FYs. Each row carries the mapped compact fields."""
    df = ak.stock_financial_abstract(symbol=sym)
    if df is None or df.empty:
        return []
    # date columns are 'YYYYMMDD' strings; keep annual (Dec-31) periods
    date_cols = [c for c in df.columns if str(c).isdigit() and len(str(c)) == 8]
    annual = sorted([c for c in date_cols if str(c).endswith("1231")])[-7:]
    if not annual:
        return []
    # build (指标 -> field) lookup, first-seen wins
    field_by_ind: dict[str, str] = {}
    for ind in df["指标"]:
        if ind in _IND and _IND[ind] not in field_by_ind.values():
            field_by_ind[ind] = _IND[ind]
    rows = []
    for col in annual:
        rec = {"fy": int(str(col)[:4])}
        for ind, field in field_by_ind.items():
            sub = df.loc[df["指标"] == ind, col]
            if not sub.empty:
                rec[field] = _num(sub.iloc[0])
        rows.append(rec)
    return rows


def _description(ak, sym: str) -> dict:
    try:
        df = ak.stock_zyjs_ths(symbol=sym)
        if df is None or df.empty:
            return {}
        r = df.iloc[0]
        return {"main_business": (r.get("主营业务") or "").strip() or None,
                "product_type": (r.get("产品类型") or "").strip() or None,
                "scope": (r.get("经营范围") or "").strip() or None}
    except Exception:  # noqa: BLE001
        return {}


def _dividends(ak, sym: str) -> dict:
    """Compact dividend read: count of cash-paying years + the latest 派息比例."""
    try:
        df = ak.stock_dividend_cninfo(symbol=sym)
        if df is None or df.empty:
            return {}
        dcol = "实施方案公告日期"
        if dcol in df.columns:
            df = df.sort_values(dcol)
        cash = df[df.get("派息比例", pd.Series(dtype=float)).apply(_num).fillna(0) > 0]
        latest = None
        if not cash.empty:
            latest = _num(cash.iloc[-1].get("派息比例"))   # most-recent cash payout
        return {"cash_years": int(len(cash)), "latest_payout_per10": latest}
    except Exception:  # noqa: BLE001
        return {}


def _shareholders(ak, sym: str) -> dict:
    """Retail-concentration tell: latest holder count + its trailing change."""
    try:
        df = ak.stock_zh_a_gdhs_detail_em(symbol=sym)
        if df is None or df.empty:
            return {}
        # the endpoint returns the full history; pick the most-recent record
        dcol = "股东户数统计截止日"
        if dcol in df.columns:
            df = df.sort_values(dcol)
        r = df.iloc[-1]
        return {"holders": _num(r.get("股东户数-本次")),
                "holders_chg_pct": _num(r.get("股东户数-增减比例")),
                "avg_hold_value": _num(r.get("户均持股市值")),
                "asof": str(r.get("股东户数统计截止日") or "") or None}
    except Exception:  # noqa: BLE001
        return {}


def fetch_one(ticker: str) -> dict | None:
    """Build one compact fundamentals record for a ticker. Returns None on hard fail."""
    import akshare as ak
    sym = ak_symbol(ticker)
    try:
        rows = _abstract_rows(ak, sym)
    except Exception as e:  # noqa: BLE001
        log.debug("%s abstract failed: %s", ticker, e)
        rows = []
    if not rows:
        return None  # no financials -> nothing worth storing
    rec = {"ticker": ticker, "financials": rows,
           "description": _description(ak, sym),
           "dividends": _dividends(ak, sym),
           "shareholders": _shareholders(ak, sym)}
    return rec


def _high_value_universe() -> list[str]:
    """The names actually surfaced on the China page — standouts + every screener
    board + the search index head — so the subset fetch covers what users click."""
    site = config.ROOT / config.load()["storage"]["site_dir"]
    fd = site / "factordata"
    tickers: set[str] = set()

    def add(path, key, sub="ticker"):
        p = fd / path
        if not p.exists():
            return
        try:
            d = json.loads(p.read_text())
        except Exception:  # noqa: BLE001
            return
        rows = d.get(key) if isinstance(d, dict) else None
        for r in (rows or []):
            t = r.get(sub) if isinstance(r, dict) else None
            if t:
                tickers.add(t)

    add("china_setups.json", "buy")
    add("china_reversal.json", "watch")
    add("china_lowvol.json", "sleeve")
    add("china_alpha.json", "top")
    # search-index head (most-liquid names) as a backstop so the panel isn't empty
    idx = site / "chinastockdata" / "index.json"
    if idx.exists():
        try:
            for r in json.loads(idx.read_text())[:60]:
                if r.get("t"):
                    tickers.add(r["t"])
        except Exception:  # noqa: BLE001
            pass
    return sorted(tickers)


def _full_universe() -> list[str]:
    p = config.data_dir() / "china_search" / "members.parquet"
    if not p.exists():
        return []
    try:
        df = pd.read_parquet(p)
        col = "ticker" if "ticker" in df.columns else df.columns[0]
        return sorted(df[col].astype(str).tolist())
    except Exception:  # noqa: BLE001
        return []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="fetch the full search universe")
    ap.add_argument("--tickers", default=None, help="comma-separated explicit tickers")
    ap.add_argument("--max-age", type=int, default=20, help="skip cached names fresher than N days")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0, help="cap names this run (0 = no cap)")
    args = ap.parse_args()

    if args.tickers:
        want = [t.strip() for t in args.tickers.split(",") if t.strip()]
    elif args.all:
        want = _full_universe()
    else:
        want = _high_value_universe()
    if not want:
        log.error("no tickers to fetch")
        return 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    cache: dict[str, dict] = {}
    if OUT.exists():
        try:
            old = pd.read_parquet(OUT)
            for _, r in old.iterrows():
                cache[r["ticker"]] = {"payload": r["payload"], "asof": r["asof"]}
        except Exception as e:  # noqa: BLE001
            log.warning("cache read failed (%s); starting fresh", e)

    today = pd.Timestamp.utcnow().strftime("%Y-%m-%d")
    fresh_cut = (pd.Timestamp.utcnow() - pd.Timedelta(days=args.max_age)).strftime("%Y-%m-%d")
    todo = [t for t in want if not (t in cache and cache[t].get("asof", "") >= fresh_cut)]
    if args.limit:
        todo = todo[:args.limit]
    log.info("china fundamentals: %d requested, %d cached-fresh, %d to fetch",
             len(want), len(want) - len(todo), len(todo))

    got = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(fetch_one, t): t for t in todo}
        for fut in as_completed(futs):
            t = futs[fut]
            try:
                rec = fut.result()
            except Exception as e:  # noqa: BLE001
                log.debug("%s failed: %s", t, e)
                rec = None
            if rec:
                cache[t] = {"payload": json.dumps(rec, ensure_ascii=False, default=str),
                            "asof": today}
                got += 1
                if got % 25 == 0:
                    log.info("  ... %d/%d fetched", got, len(todo))

    if cache:
        out = pd.DataFrame([{"ticker": k, "payload": v["payload"], "asof": v["asof"]}
                            for k, v in sorted(cache.items())])
        out.to_parquet(OUT, index=False)
        log.info("wrote %s (%d names total, +%d this run)", OUT, len(out), got)
    return 0


if __name__ == "__main__":
    sys.exit(main())
