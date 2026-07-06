"""Wikipedia pageview backfill to 2015-07-01.

Extends data/attention/<TICKER>.parquet from the existing ~126 days on disk to
full history starting 2015-07-01 (earliest available from the Wikimedia REST API).

Strategy:
- Read existing parquet; determine the earliest date already on disk.
- If earliest date > 2015-07-01, fetch the missing tail in one API call
  (the per-article endpoint accepts any date range).
- Merge old + new, deduplicate, write back.
- Tickers without a resolved wiki_title are skipped (same as the live collector).
- Resumable: re-running skips tickers already complete.

Throttle: configurable, default 0.05 s/req (<= 20 req/s).
Output: data/attention/<TICKER>.parquet updated in place.
"""
from __future__ import annotations

import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import numpy as np
import pandas as pd
import requests

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(ROOT))

from collectors.equity_profile import WIKI_UA  # noqa: E402
from collectors.wiki_pageviews import _parse  # noqa: E402
from lib import config  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

BACKFILL_START = "20150701"
PACE_SEC = 0.05
RETRIES = 3
TIMEOUT = 30

BASE_URL = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"


def _url(title: str, start: str, end: str) -> str:
    return (
        f"{BASE_URL}/en.wikipedia.org/all-access/user/"
        f"{quote(title.replace(' ', '_'), safe='')}"
        f"/daily/{start}/{end}"
    )


def _fetch_range(title: str, start: str, end: str) -> pd.DataFrame:
    """Fetch pageviews for one ticker/title for the given date range."""
    url = _url(title, start, end)
    for attempt in range(RETRIES):
        try:
            r = requests.get(url, headers={"User-Agent": WIKI_UA}, timeout=TIMEOUT)
            if r.status_code == 404:
                return pd.DataFrame()  # article not found or date range out of bounds
            r.raise_for_status()
            return _parse(r.json())
        except Exception as exc:
            if attempt == RETRIES - 1:
                log.warning("SKIP %s (error after %d retries): %s", title, RETRIES, exc)
                return pd.DataFrame()
            time.sleep(1.0)
    return pd.DataFrame()


def _ticker_titles() -> dict[str, str]:
    path = config.data_dir() / "profile" / "profiles.parquet"
    if not path.exists():
        return {}
    df = pd.read_parquet(path)
    if "wiki_title" not in df.columns:
        return {}
    s = df["wiki_title"].dropna()
    return {str(tk): str(t) for tk, t in s.items() if str(t).strip()}


def backfill(attention_dir: Path, pace_sec: float = PACE_SEC) -> dict:
    titles = _ticker_titles()
    log.info("Found %d tickers with wiki_title", len(titles))

    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    target_start = pd.Timestamp(BACKFILL_START)

    skipped_no_title = 0
    skipped_already_complete = 0
    extended = 0
    failed = 0
    total_new_rows = 0

    parquet_files = {p.stem: p for p in attention_dir.glob("*.parquet")}

    # Process tickers that have an existing parquet file
    for tk, path in parquet_files.items():
        if tk not in titles:
            skipped_no_title += 1
            continue

        title = titles[tk]
        existing = pd.read_parquet(path)

        existing_start = existing.index.min()
        if pd.isna(existing_start):
            existing_start = pd.Timestamp.today()

        if existing_start <= target_start + pd.Timedelta(days=5):
            skipped_already_complete += 1
            continue

        # Fetch from 2015-07-01 to one day before existing_start
        fetch_end = (existing_start - pd.Timedelta(days=1)).strftime("%Y%m%d")
        new_df = _fetch_range(title, BACKFILL_START, fetch_end)
        time.sleep(pace_sec)

        if new_df.empty:
            failed += 1
            log.debug("No data for %s (%s)", tk, title)
            continue

        # Merge and deduplicate
        merged = pd.concat([new_df, existing]).sort_index()
        merged = merged[~merged.index.duplicated(keep="last")]
        merged.to_parquet(path)
        total_new_rows += len(new_df)
        extended += 1

        if extended % 50 == 0:
            log.info("Progress: %d extended, %d failed, %d already_complete",
                     extended, failed, skipped_already_complete)

    log.info(
        "Backfill complete: %d extended (%d new rows), %d already complete, "
        "%d failed, %d skipped (no wiki_title)",
        extended, total_new_rows, skipped_already_complete, failed, skipped_no_title,
    )
    return {
        "titles_resolved": len(titles),
        "extended": extended,
        "already_complete": skipped_already_complete,
        "failed": failed,
        "skipped_no_title": skipped_no_title,
        "total_new_rows": total_new_rows,
    }


if __name__ == "__main__":
    attention_dir = ROOT / "data" / "attention"
    assert attention_dir.exists(), f"attention dir not found: {attention_dir}"
    stats = backfill(attention_dir)
    print("\n=== Backfill summary ===")
    for k, v in stats.items():
        print(f"  {k}: {v}")
