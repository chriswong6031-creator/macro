"""One-off seed: fetch max history for the new stock_search.extra_tickers and
store them under data/yahoo so they build/search immediately (the nightly
YahooAdapter keeps them fresh thereafter). Single-ticker .history() calls,
which dodge the bulk-download rate limit. Safe to re-run."""
from __future__ import annotations

import sys
import time

import pandas as pd
import yfinance as yf

from lib import config, store


def main() -> int:
    extras = config.load().get("stock_search", {}).get("extra_tickers", []) or []
    print("data dir:", config.data_dir())
    print("seeding", len(extras), "tickers")
    ok, bad = [], []
    for t in extras:
        if store.read("yahoo", t) is not None and "--force" not in sys.argv:
            print(f"  {t:6s} already present — skip"); ok.append(t); continue
        frame = None
        for attempt in range(4):
            try:
                h = yf.Ticker(t).history(period="max", auto_adjust=True)
                if h is not None and not h.empty and "Close" in h.columns:
                    sub = h[["Close", "Volume"]].rename(
                        columns={"Close": "close", "Volume": "volume"})
                    sub.index = pd.to_datetime(sub.index).tz_localize(None)
                    sub = sub.dropna(subset=["close"])
                    if not sub.empty:
                        frame = sub
                        break
                print(f"  {t:6s} empty (attempt {attempt})")
            except Exception as e:  # noqa: BLE001
                print(f"  {t:6s} err {str(e)[:50]} (attempt {attempt})")
            time.sleep(2 + attempt * 2)
        if frame is None:                      # Yahoo refused it — try Stooq's free CSV
            from lib.stooq import stooq_daily
            frame = stooq_daily(t)
            if frame is not None:
                print(f"  {t:6s} via Stooq")
        if frame is None:
            bad.append(t); continue
        store.upsert("yahoo", t, frame, outlier_col=None)
        last = float(frame["close"].iloc[-1])
        print(f"  {t:6s} OK rows={len(frame)} {frame.index.min().date()}..{frame.index.max().date()} last={last:.2f}")
        ok.append(t)
        time.sleep(1)
    print(f"\nseeded OK: {len(ok)}  | FAILED: {bad}")
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
