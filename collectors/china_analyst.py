"""Analyst consensus for A-share names (keyless, via akshare/Eastmoney).

The A-share parallel of the analyst-consensus read HK already surfaces
(engine/hk_fundamentals._consensus) and the gap the US page still has open. One
WHOLE-MARKET call returns, per name, the sell-side picture Eastmoney aggregates:

  stock_profit_forecast_em("")  -> 研报数 (coverage / report count), the six-month
                                   institutional rating mix (买入/增持/中性/减持/卖出),
                                   and forward EPS forecasts for the next ~4 fiscal years.

Stored compactly under data/china_analyst/forecast.parquet ({ticker, payload, asof}),
refreshed every build (one cheap call, no per-name loop). The engine
(engine/china_extras.analyst_consensus) buckets the ratings into buy/hold/sell, picks
the current + next forecast year, and — with the live price — derives a forward P/E.

CONTEXT, NOT A SIGNAL. Sell-side targets/ratings are opinion, shown as coverage
context to read alongside the validated reversal / low-vol signals — never a buy
ranking (A-share residual momentum is not a validated edge; research/CHINA_HK_STOCK_SIGNALS.md).
"""
from __future__ import annotations

import argparse
import json
import logging

import pandas as pd

from lib import config

log = logging.getLogger("china_analyst")

OUT = config.data_dir() / "china_analyst" / "forecast.parquet"

# Eastmoney bare 6-digit code -> our ticker suffix. A-shares: 6/9 = Shanghai,
# 688 STAR = Shanghai, 0/3 = Shenzhen, 4/8 = Beijing (BSE).
def to_ticker(code: str) -> str | None:
    c = "".join(ch for ch in str(code) if ch.isdigit()).zfill(6)
    if len(c) != 6:
        return None
    if c[0] in ("6", "9") or c.startswith("688"):
        return f"{c}.SS"
    if c[0] in ("0", "2", "3"):
        return f"{c}.SZ"
    if c[0] in ("4", "8"):
        return f"{c}.BJ"
    return None


def _num(v):
    try:
        if v in (None, "", "--", "—"):
            return None
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def _forecast_years(cols: list[str]) -> list[tuple[int, str]]:
    """[(year, column)] for every '<YYYY>预测每股收益' column, ascending by year."""
    out = []
    for c in cols:
        s = str(c)
        if "预测每股收益" in s:
            digits = "".join(ch for ch in s if ch.isdigit())[:4]
            if len(digits) == 4:
                out.append((int(digits), c))
    return sorted(out)


def fetch_table() -> pd.DataFrame | None:
    """The whole-market Eastmoney profit-forecast table. Returns None on failure."""
    import akshare as ak
    try:
        df = ak.stock_profit_forecast_em(symbol="")
    except Exception as e:  # noqa: BLE001 — one broken scrape must never break the build
        log.warning("china analyst: profit_forecast_em failed (%s)", e)
        return None
    return df if df is not None and not df.empty else None


def refresh() -> int:
    """Fetch the whole-market forecast table once and bake a compact per-ticker
    payload. Best-effort: returns the number of names written (0 on failure).
    Overwrites the cache each run (the source is a same-day snapshot, fully
    re-fetchable — no need to accrue history). Idempotent within a day: a cache already
    stamped with today's UTC date is left untouched (so it runs once per CI day even if
    several builds call it)."""
    today = pd.Timestamp.utcnow().strftime("%Y-%m-%d")
    if OUT.exists():
        try:
            if str(pd.read_parquet(OUT, columns=["asof"])["asof"].max()) >= today:
                log.info("china analyst: cache already fresh (%s)", today)
                return 0
        except Exception:  # noqa: BLE001
            pass
    df = fetch_table()
    if df is None:
        return 0
    years = _forecast_years(list(df.columns))
    rate = {  # rating column -> bucket
        "机构投资评级(近六个月)-买入": "buy", "机构投资评级(近六个月)-增持": "overweight",
        "机构投资评级(近六个月)-中性": "neutral", "机构投资评级(近六个月)-减持": "underweight",
        "机构投资评级(近六个月)-卖出": "sell",
    }
    rows = []
    for _, r in df.iterrows():
        t = to_ticker(r.get("代码"))
        if not t:
            continue
        rec: dict = {"reports": int(_num(r.get("研报数")) or 0)}
        for col, key in rate.items():
            rec[key] = int(_num(r.get(col)) or 0)
        rec["eps"] = {str(y): _num(r.get(col)) for y, col in years}
        rows.append({"ticker": t, "name": str(r.get("名称") or ""),
                     "payload": json.dumps(rec, ensure_ascii=False, default=str)})
    if not rows:
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    asof = today
    out = pd.DataFrame(rows)
    out["asof"] = asof
    out.to_parquet(OUT, index=False)
    log.info("china analyst: wrote %s (%d names, asof %s)", OUT, len(out), asof)
    return len(out)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    argparse.ArgumentParser().parse_args()
    return 0 if refresh() else 1


if __name__ == "__main__":
    raise SystemExit(main())
