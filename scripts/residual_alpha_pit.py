"""Phase 2 (path-to-GO) data prep — point-in-time S&P 500 membership + best-effort
delisted prices, to DE-BIAS the residual-alpha backtest (research/RESIDUAL_ALPHA_MOMENTUM.md).

The deep panel (scripts/residual_alpha_fetch.py) is CURRENT members only, so a
backtest over-credits survivors. This adds the two pieces a free-data survivorship
fix needs:
  1. WHEN each name was actually in the index — fja05680/sp500 ticker_start_end
     (1996->, Wikipedia-sourced) -> data/breadth/sp500_pit_membership.parquet.
  2. PRICES for the names that have since LEFT the index — best-effort yfinance
     -> data/breadth/_closes_delisted.parquet. Honest ceiling: many delisted /
     renamed tickers no longer resolve on Yahoo; a fully clean test needs paid
     CRSP. The harness reports exactly how much coverage was recovered.

Run once, offline:  .venv/bin/python -m scripts.residual_alpha_pit
"""
from __future__ import annotations

import io
import sys
import urllib.request
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.breadth import BreadthAdapter  # noqa: E402
from engine.equity_factors import _closes  # noqa: E402
from lib import config  # noqa: E402

CSV_URL = "https://raw.githubusercontent.com/fja05680/sp500/master/sp500_ticker_start_end.csv"


def fetch_membership() -> pd.DataFrame:
    raw = urllib.request.urlopen(CSV_URL, timeout=60).read().decode()
    df = pd.read_csv(io.StringIO(raw))
    df.columns = [c.strip().lower() for c in df.columns]
    df["ticker"] = df["ticker"].astype(str).str.replace(".", "-", regex=False).str.strip()
    df["start_date"] = pd.to_datetime(df["start_date"], errors="coerce")
    df["end_date"] = pd.to_datetime(df["end_date"], errors="coerce")   # NaT = still a member
    df = df.dropna(subset=["start_date"]).reset_index(drop=True)
    out = config.data_dir() / "breadth" / "sp500_pit_membership.parquet"
    df.to_parquet(out)
    print(f"[membership] {len(df)} intervals · {df['ticker'].nunique()} unique tickers · "
          f"from {df['start_date'].min().date()} -> {out}", flush=True)
    return df


def fetch_delisted(members: pd.DataFrame) -> None:
    pit = set(members["ticker"])
    have = set(_closes().columns)
    missing = sorted(pit - have)
    print(f"[delisted] {len(pit)} historical members · already have {len(pit & have)} "
          f"({100 * len(pit & have) // len(pit)}%) · fetching {len(missing)} missing "
          f"(best-effort, many won't resolve) …", flush=True)
    closes = BreadthAdapter()._download_closes(missing, "max")
    closes = closes.loc[:, ~closes.columns.duplicated()].dropna(axis=1, how="all").sort_index()
    got = [t for t in missing if t in closes.columns]
    closes = closes[got]
    out = config.data_dir() / "breadth" / "_closes_delisted.parquet"
    closes.to_parquet(out)
    recovered = len(pit & have) + len(got)
    print(f"[delisted] resolved {len(got)}/{len(missing)} of the missing "
          f"({100 * len(got) // max(len(missing), 1)}%) -> {out} {closes.shape}", flush=True)
    print(f"[coverage] PIT price coverage now {recovered}/{len(pit)} "
          f"({100 * recovered // len(pit)}%) — the rest is the irreducible free-data gap.", flush=True)


def main() -> int:
    fetch_delisted(fetch_membership())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
