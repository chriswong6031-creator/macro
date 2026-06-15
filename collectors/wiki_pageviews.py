"""Per-ticker OFFSHORE attention from Wikimedia Pageviews (keyless, no auth).

Feeds a DISPLAY-ONLY over-extension / fade-risk caution chip on discovery.html and
stock.html — never a scored leg, never directional (see research/WIKI_ATTENTION_CHIP
_SPEC.md and the Phase-0 harness scripts/wiki_attention_phase0.py). The honest prior
(Da-Engelberg-Gao 2011, "In Search of Attention") is that an attention SPIKE precedes
short-horizon price REVERSAL — concentrated in small/illiquid names our liquid universe
excludes, and decayed since the 2021 meme era — so this is crowding/extension context,
not edge.

Source: wikimedia.org/api/rest_v1/metrics/pageviews/per-article — daily views per English
Wikipedia article, agent=user (humans, bots excluded). en.wikipedia.org counts OFFSHORE
attention only: for CN/HK-domiciled names the mainland audience is GFW-blind to the article,
so the chip carries an "international attention only" caveat (the templates gate that on the
ticker suffix). The endpoint serves from 2015-07-01.

Ticker -> article: reuses the namesake-robust resolution in collectors.equity_profile
(opensearch -> _is_company_page -> _match_score) via the `wiki_title` column it now persists
into data/profile/profiles.parquet. A ticker without a resolved title is simply skipped (no
chip); a fully-empty result raises so run_adapter degrades rather than crashing the run.
Stored as a two-column (views, log_views) frame so store.upsert's single-column outlier guard
does NOT quarantine legitimate viral spikes — those spikes ARE the signal.
"""
from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

import numpy as np
import pandas as pd

from collectors.base import Adapter
from collectors.equity_profile import WIKI_UA
from lib import config

log = logging.getLogger(__name__)

API_FLOOR = date(2015, 7, 1)   # /per-article serves no earlier


def _ticker_titles() -> dict[str, str]:
    """{ticker: validated Wikipedia article title} from profiles.parquet's `wiki_title`
    column (populated by collectors.equity_profile, which now persists the resolved page
    title). Tickers without a resolved title are skipped — they just get no chip. Returns
    {} when the column is absent entirely (profiles not yet re-fetched) → the adapter then
    raises and run_adapter degrades gracefully."""
    p = config.data_dir() / "profile" / "profiles.parquet"
    if not p.exists():
        return {}
    try:
        df = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001 — best-effort
        log.warning("wiki_pageviews: profiles.parquet unreadable (%s)", e)
        return {}
    if "wiki_title" not in df.columns:
        return {}
    out: dict[str, str] = {}
    for tk, title in df["wiki_title"].items():
        if isinstance(title, str) and title.strip():
            out[str(tk)] = title.strip()
    return out


def _parse(payload: dict) -> pd.DataFrame:
    """Wikimedia per-article JSON -> date-indexed (views, log_views) frame. The response
    is {"items": [{"timestamp": "YYYYMMDDHH", "views": N, ...}, ...]}. Two columns on
    purpose: a single-column count series would trip store.upsert's outlier guard, which
    would quarantine the viral spikes this signal exists to measure."""
    items = (payload or {}).get("items") or []
    idx, vals = [], []
    for it in items:
        ts, v = it.get("timestamp"), it.get("views")
        if ts is None or v is None:
            continue
        idx.append(pd.to_datetime(str(ts)[:8], format="%Y%m%d"))
        vals.append(float(v))
    if not idx:
        raise ValueError("wiki_pageviews: no parseable rows in response")
    s = pd.Series(vals, index=pd.DatetimeIndex(idx)).sort_index()
    s = s[~s.index.duplicated(keep="last")]
    return pd.DataFrame({"views": s, "log_views": np.log1p(s)})


class WikiPageviewsAdapter(Adapter):
    """Daily English-Wikipedia pageviews per universe ticker (offshore attention)."""

    name = "wiki_pageviews"
    group = "attention"            # new data/attention/ dir, one parquet per ticker
    stale_after_days = 4           # daily series; small slack for the API's ~1-2d lag
    expected_failure = None        # endpoint is reachable; per-ticker misses tolerated

    def __init__(self) -> None:
        self.cfg = config.load()["wiki_pageviews"]
        self.url = (str(self.cfg["base_url"]).rstrip("/")
                    + "/{project}/{access}/{agent}/{article}/daily/{start}/{end}")

    def _window(self, full_history: bool) -> tuple[str, str]:
        win = int(self.cfg["history_days_full"] if full_history else self.cfg["history_days"])
        end = datetime.now(timezone.utc).date()
        start = max(end - timedelta(days=win), API_FLOOR)
        return start.strftime("%Y%m%d"), end.strftime("%Y%m%d")

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        titles = _ticker_titles()
        if not titles:
            raise ValueError("wiki_pageviews: no wiki_title in profiles.parquet — run "
                             "collectors.equity_profile to backfill the column first")
        start, end = self._window(full_history)
        min_days = int(self.cfg.get("min_days", 60))
        retries = int(self.cfg.get("retries", 3))
        pace = float(self.cfg.get("pace_sec", 0.05))
        proj, acc, agt = self.cfg["project"], self.cfg["access"], self.cfg["agent"]
        frames: dict[str, pd.DataFrame] = {}
        for tk, title in titles.items():
            art = quote(str(title).replace(" ", "_"), safe="")
            url = self.url.format(project=proj, access=acc, agent=agt, article=art,
                                  start=start, end=end)
            try:
                r = self.http_get(url, retries=retries, headers={"User-Agent": WIKI_UA})
                df = _parse(r.json())
                if len(df) >= min_days:
                    frames[tk] = df
            except Exception as e:  # noqa: BLE001 — one bad article never kills the run
                log.debug("wiki_pageviews %s (%s) skipped: %s", tk, title, e)
            finally:
                if pace:
                    time.sleep(pace)
        if not frames:
            raise ValueError("wiki_pageviews: no article resolved to views")
        log.info("wiki_pageviews: %d/%d tickers fetched (%s..%s)",
                 len(frames), len(titles), start, end)
        return frames
