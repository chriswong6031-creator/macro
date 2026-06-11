"""Stopgap: populate FRED series history from recent Wayback Machine captures
of fredgraph.csv when the live endpoint is down (it 504s for extended windows;
observed during the initial build). The store's upsert is append-only, so live
data simply layers the most recent days on top once FRED recovers.

Usage: python -m scripts.fred_wayback_fallback [--max-age-days 30]
Only fills series that are missing or older than the freshest capture found.
"""
from __future__ import annotations

import argparse
import io
import sys
import time
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config, store  # noqa: E402

CDX = "https://web.archive.org/cdx/search/cdx"
UA = {"User-Agent": "macro-dashboard/1.0 (research; archived-data fallback)"}


def latest_capture(series_id: str) -> str | None:
    target = f"fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    r = requests.get(CDX, params={"url": target, "output": "json", "limit": "-5",
                                  "filter": "statuscode:200"}, headers=UA, timeout=60)
    r.raise_for_status()
    rows = r.json()
    if len(rows) < 2:
        return None
    return rows[-1][1]  # newest timestamp


def fetch_capture(series_id: str, ts: str, col: str) -> pd.DataFrame:
    url = (f"https://web.archive.org/web/{ts}id_/"
           f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}")
    r = requests.get(url, headers=UA, timeout=120)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    if df.shape[1] != 2:
        raise ValueError(f"unexpected capture shape for {series_id}: {df.shape}")
    df.columns = ["date", col]
    df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna().set_index("date")
    df.index = pd.to_datetime(df.index)
    return df


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-age-days", type=int, default=30,
                    help="skip series whose stored data is already fresher than this")
    args = ap.parse_args()

    fred_cfg = config.load()["fred"]["series"]
    series: dict[str, str] = {}
    for grp in fred_cfg.values():
        series.update(grp)

    today = pd.Timestamp.today().normalize()
    for sid, col in series.items():
        last = store.last_date("fred", sid)
        if last is not None and (today - pd.Timestamp(last)).days <= args.max_age_days:
            print(f"{sid}: stored through {last}, skip")
            continue
        try:
            ts = latest_capture(sid)
            if ts is None:
                print(f"{sid}: NO wayback capture found")
                continue
            df = fetch_capture(sid, ts, col)
            store.upsert("fred", sid, df, outlier_col=col)
            print(f"{sid}: capture {ts[:8]} -> {len(df)} rows "
                  f"{df.index.min().date()}..{df.index.max().date()}")
        except Exception as e:  # noqa: BLE001
            print(f"{sid}: FAILED {type(e).__name__}: {e}")
        time.sleep(2)  # be polite to web.archive.org


if __name__ == "__main__":
    main()
