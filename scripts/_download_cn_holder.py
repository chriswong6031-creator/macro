#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Standalone download script for 减持 data. Run this directly."""
import requests
import time
import pandas as pd
import numpy as np
from pathlib import Path

OUT = Path("/Users/chriswong/Documents/Cluade/Macro Dashboard/data/cn_holder_sales")
OUT.mkdir(exist_ok=True)

URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
HEADERS = {"User-Agent": "Mozilla/5.0"}
COLS = (
    "SECURITY_CODE,SECURITY_NAME_ABBR,NOTICE_DATE,START_DATE,END_DATE,"
    "HOLDER_NAME,CHANGE_NUM,HOLD_RATIO,CHANGE_NUM_SYMBOL,MARKET,"
    "FREE_SHARES,AFTER_HOLDER_NUM,TRADE_DATE,CHANGE_RATE,AFTER_CHANGE_RATE"
)
FILTER_STR = '(DIRECTION="减持")'

all_data = []
for page in range(1, 225):
    params = {
        "reportName": "RPT_SHARE_HOLDER_INCREASE",
        "columns": COLS,
        "pageNumber": str(page),
        "pageSize": "500",
        "sortColumns": "NOTICE_DATE",
        "sortTypes": "-1",
        "source": "WEB",
        "client": "WEB",
        "filter": FILTER_STR,
    }
    for attempt in range(3):
        try:
            r = requests.get(URL, params=params, headers=HEADERS, timeout=20)
            d = r.json()
            rows = (d.get("result") or {}).get("data") or []
            all_data.extend(rows)
            break
        except Exception as e:
            if attempt == 2:
                print(f"Page {page} failed: {e}")
            time.sleep(1)
    if page % 20 == 0:
        print(f"Page {page}/224: {len(all_data)} records", flush=True)
    time.sleep(0.3)

print(f"Total downloaded: {len(all_data)}")
df = pd.DataFrame(all_data)

# Clean
for col in ("NOTICE_DATE", "START_DATE", "END_DATE", "TRADE_DATE"):
    df[col] = pd.to_datetime(df[col], errors="coerce").dt.normalize()
for col in ("CHANGE_NUM", "HOLD_RATIO", "CHANGE_NUM_SYMBOL", "FREE_SHARES",
            "AFTER_HOLDER_NUM", "CHANGE_RATE", "AFTER_CHANGE_RATE"):
    df[col] = pd.to_numeric(df[col], errors="coerce")

df["shares_sold"] = df["CHANGE_NUM"].abs() * 1e4
mask = df["HOLD_RATIO"].notna() & (df["HOLD_RATIO"] > 0) & df["AFTER_HOLDER_NUM"].notna()
df["total_shares_wan"] = np.where(mask, df["AFTER_HOLDER_NUM"] / df["HOLD_RATIO"] * 100.0, np.nan)
df["window_open"] = df["START_DATE"].fillna(df["END_DATE"] - pd.Timedelta(days=30))
df["window_close"] = df["END_DATE"].fillna(df["NOTICE_DATE"])

def _suffix(code):
    c = str(code).strip()
    return f"{c}.SH" if c.startswith("6") else f"{c}.SZ"

df["ticker"] = df["SECURITY_CODE"].apply(_suffix)
df = df.dropna(subset=["END_DATE"])
df = df[df["MARKET"].isin(["二级市场", "大宗交易"])].copy().reset_index(drop=True)

df.to_parquet(OUT / "raw.parquet", index=False)
print(f"Saved raw: {len(df)} rows -> {OUT/'raw.parquet'}")
print(f"Date range: {df.END_DATE.min().date()} .. {df.END_DATE.max().date()}")
print(f"Unique tickers: {df.ticker.nunique()}")
print(f"pct_float derivable: {mask.sum()}")
