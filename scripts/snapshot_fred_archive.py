"""One-shot: write data/archive/<SERIES_ID>.parquet for the 9 CCW-W1 rolling BAML
series that FRED now serves as a rolling 3-year window.

These series are enrolled in config.yml [fred][series][corp_credit] (added CCW-W1).
Because FRED truncates the history after April 2026 the archive snapshot must be
seeded from the live fredgraph.csv (which still returns 3y of data) or from an
already-populated data/fred/<SERIES_ID>.parquet if one exists.

Idempotent: skips series whose archive file already exists.

Archive format (mirrors data/archive/BAMLC0A0CM.parquet and BAMLH0A0HYM2.parquet):
  - DatetimeIndex named 'date'
  - Single column named by the config alias (e.g. 'aaa_oas')
  - float64 values

Usage (one-shot, run once after CCW-W1 PR lands):
    python -m scripts.snapshot_fred_archive

Law: call lib.procutil.hard_exit() at end — this script reads parquet via pyarrow
and the Arrow ThreadPool static-destructor deadlock (#2196) would hang it forever.
"""
from __future__ import annotations

import io
import logging
import sys
from pathlib import Path

import pandas as pd
import requests
from requests.utils import default_user_agent

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import config  # noqa: E402
from lib.procutil import hard_exit  # noqa: E402

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO,
                    format="%(levelname)s %(name)s: %(message)s")

# ---------------------------------------------------------------------------
# The 9 CCW-W1 BAML corp_credit series (§2.2 / R12 / §6-W1).
# DGS20 is excluded — it has deep history and needs no archive.
# Mapping: FRED series ID → config alias (from config.yml [fred][series][corp_credit])
# ---------------------------------------------------------------------------
SERIES = {
    "BAMLC0A1CAAA":   "aaa_oas",
    "BAMLC0A2CAA":    "aa_oas",
    "BAMLC0A3CA":     "a_oas",
    "BAMLC0A4CBBB":   "bbb_oas",
    "BAMLH0A1HYBB":   "bb_oas",
    "BAMLH0A2HYB":    "b_oas",
    "BAMLC0A0CMEY":   "ig_eff_yield",
    "BAMLH0A0HYM2EY": "hy_eff_yield",
    "BAMLCC0A0CMTRIV": "ig_total_return",
}

# Same UA that collectors/fred.py uses for keyless fredgraph.csv fetches
FREDGRAPH_UA = default_user_agent()
FREDGRAPH_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"


def _fetch_from_fred_parquet(sid: str, col: str, fred_dir: Path) -> pd.DataFrame | None:
    """Try to load from data/fred/<sid>.parquet (populated by the normal collector)."""
    p = fred_dir / f"{sid}.parquet"
    if not p.exists():
        return None
    df = pd.read_parquet(p)
    # fred store: DatetimeIndex named 'date', column named by alias
    if col not in df.columns:
        log.warning("%s: fred parquet exists but column %r not found (cols=%s)",
                    sid, col, list(df.columns))
        return None
    out = df[[col]].copy()
    out.index.name = "date"
    out = out.dropna()
    log.info("%s: loaded %d rows from fred store (%s..%s)",
             sid, len(out), out.index.min().date(), out.index.max().date())
    return out


def _fetch_from_fredgraph_csv(sid: str, col: str, retries: int = 4,
                               backoff_base: float = 3.0) -> pd.DataFrame | None:
    """Fetch the rolling 3y window from fredgraph.csv (keyless fallback).

    Uses the same UA idiom as collectors/fred.py to avoid FRED's bot-protection WAF.
    """
    url = f"{FREDGRAPH_CSV_URL}?id={sid}"
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            r = requests.get(url,
                             headers={"User-Agent": FREDGRAPH_UA},
                             timeout=90)
            r.raise_for_status()
            df = pd.read_csv(io.StringIO(r.text))
            if df.shape[1] != 2:
                raise ValueError(f"unexpected shape {df.shape}: cols={list(df.columns)}")
            # fredgraph.csv col 0: 'DATE' or 'observation_date'; col 1: the value
            df.columns = ["date", col]
            df[col] = pd.to_numeric(df[col], errors="coerce")
            df = df.dropna()
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
            df = df.dropna(subset=["date"]).set_index("date")
            df.index.name = "date"
            log.info("%s: fetched %d rows from fredgraph.csv (%s..%s)",
                     sid, len(df), df.index.min().date(), df.index.max().date())
            return df
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            wait = backoff_base * (2 ** attempt)
            log.warning("%s: fredgraph.csv attempt %d/%d failed (%s); retrying in %.0fs",
                        sid, attempt + 1, retries, exc, wait)
            import time
            time.sleep(wait)
    log.error("%s: all %d fredgraph.csv attempts failed: %s", sid, retries, last_exc)
    return None


def run() -> None:
    cfg = config.load()
    data_root = config.data_dir()
    fred_dir = data_root / "fred"
    archive_dir = data_root / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)

    fred_cfg = cfg["fred"]
    retries = fred_cfg.get("retries", 4)
    backoff_base = fred_cfg.get("backoff_base_s", 3.0)

    results: dict[str, str] = {}  # sid -> outcome summary for final report

    for sid, col in SERIES.items():
        dest = archive_dir / f"{sid}.parquet"
        if dest.exists():
            df = pd.read_parquet(dest)
            log.info("%s: archive already exists (%d rows %s..%s) — skipping",
                     sid, len(df), df.index.min().date(), df.index.max().date())
            results[sid] = (f"skipped (exists): {len(df)} rows "
                            f"{df.index.min().date()}..{df.index.max().date()}")
            continue

        # Try the fred store first (faster, avoids a network hit)
        df = _fetch_from_fred_parquet(sid, col, fred_dir)

        if df is None:
            # Fall back to keyless fredgraph.csv
            df = _fetch_from_fredgraph_csv(sid, col,
                                           retries=retries,
                                           backoff_base=float(backoff_base))

        if df is None or df.empty:
            log.error("%s: could not obtain data — archive NOT written", sid)
            results[sid] = "FAILED: no data obtained"
            continue

        df.to_parquet(dest)
        results[sid] = (f"written: {len(df)} rows "
                        f"{df.index.min().date()}..{df.index.max().date()} → {dest}")
        log.info("%s: wrote archive → %s", sid, dest)

    # Final summary
    print("\n=== snapshot_fred_archive results ===")
    for sid, outcome in results.items():
        print(f"  {sid}: {outcome}")


if __name__ == "__main__":
    run()
    hard_exit(0)
