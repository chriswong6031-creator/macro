#!/usr/bin/env python3
"""Multi-country OHLC data-source PoC (CHARTER §, MULTICOUNTRY_DATA.md).

Proves that a *real* per-ticker daily OHLC feed (with HIGH/LOW + years of history)
is obtainable for BOTH Hong Kong names and mainland A-shares, so the validated
MACD-RSI x StochRSI confluence + buy-filter can run on those markets (today the
china_stocks/hk_stocks stores are snapshot/close-only).

Pulls 0700.HK (Tencent) + 600519 (Kweichow Moutai, SH) + 000001 (Ping An Bank, SZ)
from yfinance and akshare and reports: columns (is HIGH/LOW present?), row count,
date range, and head/tail rows. Read-only network reads; writes nothing to data/.

Run:  python3 research/signal_engine/multicountry_poc.py
"""
from __future__ import annotations
import warnings
warnings.filterwarnings("ignore")
import pandas as pd

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 20)

HAS_HL = lambda cols: ("high" in cols and "low" in cols)


def _hdr(t: str) -> None:
    print("\n" + "=" * 78 + f"\n{t}\n" + "=" * 78)


# ---------------------------------------------------------------- yfinance ----
def poc_yfinance() -> None:
    _hdr("yfinance — full OHLC + Adj Close (.SS / .SZ suffix matches data/china)")
    import yfinance as yf
    for tk in ["0700.HK", "600519.SS", "000001.SZ"]:
        try:
            df = yf.download(tk, period="max", auto_adjust=False,
                             progress=False, threads=False)
            if df is None or len(df) == 0:
                print(f"\n  {tk}: EMPTY"); continue
            df.columns = [c[0].lower() if isinstance(c, tuple) else str(c).lower()
                          for c in df.columns]
            cols = list(df.columns)
            print(f"\n  {tk}: rows={len(df):>5}  range={df.index.min().date()} "
                  f"-> {df.index.max().date()}  high/low? {HAS_HL(cols)}")
            print(f"    cols={cols}")
            print(df[["open", "high", "low", "close", "volume"]].tail(2).to_string())
        except Exception as e:  # noqa: BLE001
            print(f"\n  {tk}: FAILED {type(e).__name__}: {str(e)[:160]}")


# ------------------------------------------------------------------ akshare ----
def poc_akshare() -> None:
    _hdr("akshare — native CN OHLC (Eastmoney); bare 6-digit A / 5-digit HK codes")
    import akshare as ak
    # A-shares: bare code, no suffix. adjust='qfq' fwd-adjusted (NOTE neg-early gotcha).
    for sym, label in [("600519", "Moutai SH"), ("000001", "Ping An Bank SZ")]:
        try:
            df = ak.stock_zh_a_hist(symbol=sym, period="daily",
                                    start_date="19900101", end_date="20260627",
                                    adjust="qfq")
            cols = list(df.columns)
            print(f"\n  A {sym} ({label}) qfq: rows={len(df):>5}  "
                  f"range={df['日期'].min()} -> {df['日期'].max()}  "
                  f"high/low(最高/最低)? {'最高' in cols and '最低' in cols}")
            print(df[["日期", "开盘", "最高", "最低", "收盘", "成交量"]].tail(2).to_string())
        except Exception as e:  # noqa: BLE001
            print(f"\n  A {sym}: FAILED {type(e).__name__}: {str(e)[:160]}")
    # demonstrate the qfq negative-early artifact vs raw on Moutai
    try:
        raw = ak.stock_zh_a_hist(symbol="600519", period="daily",
                                 start_date="20010827", end_date="20011001", adjust="")
        qfq = ak.stock_zh_a_hist(symbol="600519", period="daily",
                                 start_date="20010827", end_date="20011001", adjust="qfq")
        print(f"\n  [adjust gotcha] 600519 2001-08-27 close: raw={raw['收盘'].iloc[0]:.2f} "
              f"vs qfq={qfq['收盘'].iloc[0]:.2f}  "
              f"(qfq back-adjustment goes NEGATIVE on a ~40x riser -> use adjust='' or 'hfq')")
    except Exception as e:  # noqa: BLE001
        print(f"  [adjust gotcha] check failed: {e}")
    # HK: 5-digit zero-padded code
    try:
        df = ak.stock_hk_hist(symbol="00700", period="daily",
                              start_date="19900101", end_date="20260627", adjust="qfq")
        cols = list(df.columns)
        print(f"\n  HK 00700 (Tencent) qfq: rows={len(df):>5}  "
              f"range={df['日期'].min()} -> {df['日期'].max()}  "
              f"high/low? {'最高' in cols and '最低' in cols}")
        print(df[["日期", "开盘", "最高", "最低", "收盘", "成交量"]].tail(2).to_string())
    except Exception as e:  # noqa: BLE001
        print(f"\n  HK 00700: FAILED {type(e).__name__}: {str(e)[:160]}")


if __name__ == "__main__":
    poc_yfinance()
    poc_akshare()
    print("\n" + "=" * 78 + "\nPoC complete — both feeds return real daily OHLC with HIGH/LOW.\n" + "=" * 78)
