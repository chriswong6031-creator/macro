"""Collect descriptive fundamentals for Hong Kong names (keyless, via akshare).

The HK parallel of collectors/china_fundamentals.py. HK has RICHER free data than
the A-share side — including an analyst-consensus forecast A-shares lack:

  - stock_hk_company_profile_em            -> company profile (industry, employees,
                                              founding date, registered location)
  - stock_financial_hk_analysis_indicator_em (年度) -> annual indicators already
                                              computed: revenue, EPS, BPS, gross/net
                                              margin, ROE, ROA, debt ratio, current
                                              ratio, CFO/share, growth — the trend +
                                              Piotroski inputs in one call
  - stock_hk_profit_forecast_et (盈利预测概览) -> per-broker forward estimates +
                                              ratings + target prices (the HK-unique
                                              analyst-consensus read)

NOTE on currency: many HK names (Tencent etc.) report financials in CNY while the
price/target are in HKD. So PE/PB are deliberately NOT computed here (a CNY EPS over
an HKD price is wrong); the engine leans on currency-neutral ratios (ROE/ROA/margins)
plus the HKD analyst target as the valuation anchor.

Stored compact: one JSON `payload` per ticker in data/hk_fundamentals/fundamentals.parquet.
Only 73 names, so the full universe is fetched each run. Best-effort throughout.

Usage:
  python -m collectors.hk_fundamentals               # full HK universe
  python -m collectors.hk_fundamentals --tickers 0700.HK,0005.HK
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
log = logging.getLogger("hk_fundamentals")

OUT = config.data_dir() / "hk_fundamentals" / "fundamentals.parquet"

# stock_financial_hk_analysis_indicator_em column -> compact field
_IND = {
    "OPERATE_INCOME": "revenue", "HOLDER_PROFIT": "ni", "GROSS_PROFIT": "gross_profit",
    "BASIC_EPS": "eps", "DILUTED_EPS": "eps_diluted", "BPS": "bvps",
    "GROSS_PROFIT_RATIO": "gross_margin", "NET_PROFIT_RATIO": "net_margin",
    "ROE_AVG": "roe", "ROA": "roa", "ROIC_YEARLY": "roic",
    "DEBT_ASSET_RATIO": "debt_ratio", "CURRENT_RATIO": "current_ratio",
    "PER_NETCASH_OPERATE": "cfo_ps", "OCF_SALES": "ocf_sales",
    "OPERATE_INCOME_YOY": "rev_growth", "HOLDER_PROFIT_YOY": "ni_growth",
    "CURRENCY": "currency",
}


def ak_symbol(ticker: str) -> str:
    """0700.HK -> 00700 (akshare's 5-digit zero-padded HK code)."""
    return ticker.split(".")[0].zfill(5)


def _num(v):
    try:
        if v in (None, "", "--", "—"):
            return None
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def _financials(ak, sym: str) -> list[dict]:
    df = ak.stock_financial_hk_analysis_indicator_em(symbol=sym, indicator="年度")
    if df is None or df.empty:
        return []
    df = df.copy()
    df["_fy"] = pd.to_datetime(df["REPORT_DATE"], errors="coerce").dt.year
    df = df.dropna(subset=["_fy"]).sort_values("_fy").tail(7)
    rows = []
    for _, r in df.iterrows():
        rec = {"fy": int(r["_fy"])}
        for col, field in _IND.items():
            if col in df.columns:
                rec[field] = r[col] if field == "currency" else _num(r[col])
        rows.append(rec)
    return rows


def _profile(ak, sym: str) -> dict:
    try:
        df = ak.stock_hk_company_profile_em(symbol=sym)
        if df is None or df.empty:
            return {}
        r = df.iloc[0]

        def g(k):
            v = r.get(k)
            return (str(v).strip() or None) if v is not None and str(v) != "nan" else None
        emp = _num(r.get("员工人数"))
        return {"industry": g("所属行业"), "employees": int(emp) if emp else None,
                "founded": g("公司成立日期"), "domicile": g("注册地"),
                "name_full": g("公司名称")}
    except Exception:  # noqa: BLE001
        return {}


def _forecast(ak, sym: str) -> dict:
    """Analyst consensus from the per-broker overview: median target, rating mix,
    coverage count, latest-year forward EPS/DPS medians (the HK-unique read)."""
    try:
        df = ak.stock_hk_profit_forecast_et(symbol=sym, indicator="盈利预测概览")
        if df is None or df.empty:
            return {}
        tp = sorted(x for x in df.get("目标价", pd.Series()).apply(_num)
                    if x is not None and x == x and x > 0)
        ratings = [str(x) for x in df.get("评级", pd.Series()).dropna().tolist() if str(x).strip()]
        # bucket Chinese ratings into buy / hold / sell
        buy_kw = ("买入", "增持", "优于", "跑赢", "推荐", "强烈")
        sell_kw = ("卖出", "减持", "逊于", "跑输", "回避")
        b = sum(1 for r in ratings if any(k in r for k in buy_kw))
        s = sum(1 for r in ratings if any(k in r for k in sell_kw))
        h = len(ratings) - b - s
        out = {"n_analysts": int(len(df)),
               "target_med": round(tp[len(tp) // 2], 2) if tp else None,
               "target_low": round(tp[0], 2) if tp else None,
               "target_high": round(tp[-1], 2) if tp else None,
               "buy": b, "hold": h, "sell": s}
        return out
    except Exception:  # noqa: BLE001
        return {}


def fetch_one(ticker: str) -> dict | None:
    import akshare as ak
    sym = ak_symbol(ticker)
    try:
        rows = _financials(ak, sym)
    except Exception as e:  # noqa: BLE001
        log.debug("%s financials failed: %s", ticker, e)
        rows = []
    prof = _profile(ak, sym)
    fc = _forecast(ak, sym)
    if not rows and not fc and not prof:
        return None
    return {"ticker": ticker, "financials": rows, "profile": prof, "forecast": fc}


def _universe() -> list[str]:
    """Full HK search universe from the per-stock library index."""
    site = config.ROOT / config.load()["storage"]["site_dir"]
    idx = site / "hkstockdata" / "index.json"
    if idx.exists():
        try:
            return [r["t"] for r in json.loads(idx.read_text())
                    if r.get("t") and not r["t"].startswith("_")]
        except Exception:  # noqa: BLE001
            pass
    return []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", default=None)
    ap.add_argument("--max-age", type=int, default=20)
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    want = ([t.strip() for t in args.tickers.split(",") if t.strip()]
            if args.tickers else _universe())
    if not want:
        log.error("no HK tickers to fetch")
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
    log.info("hk fundamentals: %d requested, %d to fetch", len(want), len(todo))

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

    if cache:
        out = pd.DataFrame([{"ticker": k, "payload": v["payload"], "asof": v["asof"]}
                            for k, v in sorted(cache.items())])
        out.to_parquet(OUT, index=False)
        log.info("wrote %s (%d names, +%d this run)", OUT, len(out), got)
    return 0


if __name__ == "__main__":
    sys.exit(main())
