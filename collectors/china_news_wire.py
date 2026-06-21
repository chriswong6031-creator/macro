"""China multi-source flash-wire tone — daily numeric series for the media-sentiment index.

The China sibling of the CCTV-tone collector (collectors/china_news.py), but instead of
the once-a-day 新闻联播 broadcast it samples the live 7×24 financial flash wires (Eastmoney
全球财经快讯 + Sina/THS/Futu) and reduces TODAY's flow to ONE crude, transparent, signed
tone number — (pro-growth keyword hits − risk/tightening hits) per item — accrued as a
daily series in data/china_news/wire_tone.parquet. The engine (engine/china_news_intel.py)
z-scores it and blends it with the CCTV tone into a "media sentiment" read (the SF-Fed Daily
News Sentiment analog). KEYLESS · DISPLAY/CONTEXT-ONLY · never scored.

One snapshot per run (the wires are realtime, not dated history), so the series builds up
forward from first deploy — exactly like the limit-breadth thermometer. akshare is imported
LAZILY inside fetch() so a missing/broken dep surfaces as a tracked adapter failure rather
than silently removing the adapter from the registry. The raw HEADLINES (for the feed + PIT
event bus) are fetched separately at build time by the engine; this collector only persists
the numeric tone so the sentiment index has a real daily history to z-score against.
"""
from __future__ import annotations

import logging
from datetime import datetime

import pandas as pd

from collectors.base import Adapter
from collectors.china_news import _NEG, _POS  # reuse the CCTV policy-tone lexicon
from lib import config

log = logging.getLogger(__name__)


def _row_text(row: dict) -> str:
    """Best-effort title+summary text from a flash row (akshare column drift tolerant)."""
    out = []
    for k, v in row.items():
        ks = str(k)
        if any(n in ks for n in ("标题", "title", "摘要", "内容", "summary", "content")):
            out.append(str(v))
    return " ".join(out) if out else " ".join(str(v) for v in row.values())


def _tone(text: str, items: int) -> float:
    pos = sum(text.count(w) for w in _POS)
    neg = sum(text.count(w) for w in _NEG)
    return (pos - neg) / max(items, 1)


class ChinaNewsWireAdapter(Adapter):
    name = "china_news_wire"
    group = "china_news"
    stale_after_days = 4   # realtime wire; tolerate weekend/CI gaps

    def __init__(self) -> None:
        self.cfg = config.load().get("china_news_intel", {}) or {}

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        try:
            import akshare as ak
        except Exception as e:  # noqa: BLE001 — surface as a tracked adapter failure
            raise RuntimeError(f"china_news_wire: akshare unavailable ({e})") from e

        sources = self.cfg.get("wire_sources") or ["stock_info_global_em"]
        cap = int(self.cfg.get("max_per_source", 60))
        text_parts: list[str] = []
        items = 0
        hit_sources = 0
        for fn_name in sources:
            fn = getattr(ak, fn_name, None)
            if fn is None:
                continue
            try:
                raw = fn()
            except Exception as e:  # noqa: BLE001 — per-source isolation
                log.debug("china_news_wire %s failed: %s", fn_name, e)
                continue
            if raw is None or len(raw) == 0:
                continue
            rows = raw.head(cap).to_dict("records")
            for r in rows:
                text_parts.append(_row_text(r))
            items += len(rows)
            hit_sources += 1

        if items == 0:
            raise RuntimeError(
                f"china_news_wire: no flashes from {len(sources)} sources")

        tone = _tone(" ".join(text_parts), items)
        today = pd.Timestamp(datetime.now().date())
        out = pd.DataFrame(
            {"tone": [float(tone)], "items": [float(items)], "sources": [float(hit_sources)]},
            index=[today])
        out.index.name = "date"
        log.info("china_news_wire: tone %.3f over %d items from %d/%d sources",
                 tone, items, hit_sources, len(sources))
        return {"wire_tone": out}
