"""Offshore (en.wikipedia.org) per-ticker pageviews -> a DISPLAY-ONLY abnormal-
attention chip. Keyless Wikimedia REST; one parquet per ticker under
data/attention/. The article title is REUSED from the profile collector's resolved
`wiki_title` (collectors/equity_profile.py), so we never re-resolve the page and
never re-incur the wrong-namesake risk that collector already solved.

A 2-column frame (views + log_views) is stored on purpose: a single-column frame
would trip run_adapter's outlier guard, which quarantines big day-over-day jumps —
but a viral attention SPIKE is precisely the signal here, so it must not be clipped.

Honest prior: attention -> short-horizon reversal / over-extension, strongest in
small/illiquid names and decayed post-GME -> the chip is a fade-risk CAUTION, never
a directional signal (Phase-0: scripts/wiki_attention_phase0.py)."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import numpy as np
import pandas as pd

from collectors.base import Adapter
from collectors.equity_profile import WIKI_UA
from lib import config

log = logging.getLogger(__name__)

URL = "{base}/{project}/{access}/{agent}/{article}/daily/{start}/{end}"


def _ticker_titles() -> dict[str, str]:
    """Ticker -> validated Wikipedia article title from the profile cache's
    `wiki_title` column. Tickers without a resolved title are simply skipped."""
    path = config.data_dir() / "profile" / "profiles.parquet"
    if not path.exists():
        return {}
    df = pd.read_parquet(path)
    if "wiki_title" not in df.columns:
        return {}
    s = df["wiki_title"].dropna()
    return {str(tk): str(t) for tk, t in s.items() if str(t).strip()}


def _parse(payload: dict) -> pd.DataFrame:
    """Wikimedia per-article response -> date-indexed (views, log_views) frame."""
    items = (payload or {}).get("items", [])
    if not items:
        return pd.DataFrame()
    df = pd.DataFrame(items)
    if "timestamp" not in df or "views" not in df:
        return pd.DataFrame()
    df["date"] = pd.to_datetime(df["timestamp"].astype(str).str[:8], format="%Y%m%d", errors="coerce")
    out = df.dropna(subset=["date"]).set_index("date")[["views"]]
    out["views"] = pd.to_numeric(out["views"], errors="coerce")
    out = out.dropna().sort_index()
    out["log_views"] = np.log1p(out["views"])      # 2nd col -> run_adapter outlier_col=None
    return out


class WikiPageviewsAdapter(Adapter):
    name = "wiki_pageviews"
    group = "attention"
    stale_after_days = 4
    expected_failure = None        # endpoint reachable; per-ticker misses tolerated

    def __init__(self) -> None:
        self.cfg = config.load()["wiki_pageviews"]

    def _url(self, title: str, start: str, end: str) -> str:
        return URL.format(base=self.cfg["base_url"], project=self.cfg["project"],
                          access=self.cfg["access"], agent=self.cfg["agent"],
                          article=quote(title.replace(" ", "_"), safe=""),
                          start=start, end=end)

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        titles = _ticker_titles()
        if not titles:
            raise ValueError("wiki_pageviews: no resolved article titles "
                             "(run equity_profile to backfill wiki_title first)")
        days = self.cfg["history_days_full"] if full_history else self.cfg["history_days"]
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=int(days))
        s, e = start.strftime("%Y%m%d"), end.strftime("%Y%m%d")
        pace = float(self.cfg.get("pace_sec", 0.05))
        frames: dict[str, pd.DataFrame] = {}
        for tk, title in titles.items():
            try:
                r = self.http_get(self._url(title, s, e), retries=self.cfg["retries"],
                                  headers={"User-Agent": WIKI_UA}, timeout=30)
                df = _parse(r.json())
                if len(df) >= self.cfg["min_days"]:
                    frames[tk] = df
            except Exception:  # noqa: BLE001 — one bad article never kills the run
                continue
            time.sleep(pace)
        if not frames:
            raise ValueError("wiki_pageviews: no article resolved to views")
        log.info("wiki_pageviews: %d/%d tickers fetched", len(frames), len(titles))
        return frames
