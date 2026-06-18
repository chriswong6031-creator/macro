"""China official policy-tone — CCTV 新闻联播 (Xinwen Lianbo) daily broadcast.

新闻联播 is the 19:00 CCTV national news bulletin, the canonical daily readout of
the Party-State's priorities. Its lead-item ordering and word choice are a long-
studied proxy for official policy tone — pro-growth / easing vs risk / tightening.
This collector ACCRUES a sparse daily tone series from the broadcast text; the
engine (engine/china_news.py) z-scores + smooths it (config tone_window /
tone_smooth) into the "📰 Macro news, sentiment & catalysts" panel on china.html.
KEYLESS, DISPLAY-ONLY, never scored — see the `china_news` block in config.yml.

Source: ``ak.news_cctv(date="YYYYMMDD")`` (akshare, free, no key — wraps cctv.com's
archive; history from ~2016). One HTTP call per day, so we walk a short window:
``backfill_days`` on --full-history, ``incremental_days`` each run (re-fetched to
fill weekend / holiday / publication-lag gaps; store.upsert keeps history append-
only and lets later prints win on a date collision).

akshare is imported LAZILY inside fetch() — NOT at module top — on purpose: a
missing or broken akshare can then never make this adapter VANISH from the
registry (the silent-skip failure mode that quietly froze the China collectors
before akshare was pinned in requirements.txt). With the lazy import the module
always loads, china_news always registers, and a bad dep instead surfaces as a
normal adapter failure the circuit breaker tracks and the status page shows.

Stored under group `china_news`, one parquet:
  cctv_tone  (columns: tone, items, chars) — all NUMERIC daily features.
The per-day `tone` is a deliberately CRUDE, transparent lexicon proxy:
(pro-growth keyword hits − risk/tightening keyword hits) per broadcast item. The
engine reads it RELATIVE (z-scored over a trailing window), never as an absolute
sentiment, so the exact lexicon only has to be consistent, not authoritative.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta

import pandas as pd

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)

# Crude, transparent, clearly-signed policy-tone lexicon. Z-scored downstream, so
# ever-present boilerplate (安全/稳定/团结) is intentionally excluded — only words
# whose frequency actually MOVES with the policy stance earn a place.
_POS = (
    "增长", "发展", "改革", "开放", "支持", "促进", "提升", "优化", "扩大", "复苏",
    "回升", "向好", "繁荣", "合作", "共赢", "信心", "机遇", "宽松", "降准", "降息",
    "减税", "利好", "提振", "强劲", "突破", "推进", "增强", "加快", "高质量", "就业",
    "民生", "增收", "红利", "活力", "升级",
)
_NEG = (
    "风险", "下行", "压力", "困难", "挑战", "冲突", "制裁", "紧张", "危机", "严峻",
    "打击", "整治", "违规", "处罚", "收紧", "放缓", "衰退", "动荡", "矛盾", "损失",
    "事故", "灾害", "疫情", "通胀", "失业", "债务", "违约", "警惕", "遏制", "下滑",
    "萎缩", "恶化",
)


def _tone_features(raw: pd.DataFrame) -> dict[str, float]:
    """One day's news_cctv frame -> numeric features {tone, items, chars}.

    Pure + network-free so it unit-tests on an inline fixture. Robust to akshare
    column drift: every non-date column is treated as broadcast text.
    """
    cols = [c for c in raw.columns if str(c).lower() != "date"]
    if not cols:                       # nothing but a date column -> no text
        cols = list(raw.columns)
    text = "".join(str(v) for c in cols for v in raw[c].tolist())
    items = int(len(raw))
    chars = len(text)
    pos = sum(text.count(w) for w in _POS)
    neg = sum(text.count(w) for w in _NEG)
    tone = (pos - neg) / max(items, 1)
    return {"tone": float(tone), "items": float(items), "chars": float(chars)}


class ChinaNewsAdapter(Adapter):
    name = "china_news"
    group = "china_news"
    stale_after_days = 6   # daily bulletin, but tolerate the archive's publication lag

    def __init__(self) -> None:
        self.cfg = config.load().get("china_news", {}) or {}

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        try:
            import akshare as ak
        except Exception as e:  # noqa: BLE001 — surface as a tracked adapter failure
            raise RuntimeError(f"china_news: akshare unavailable ({e})") from e

        days = int(self.cfg.get("backfill_days", 120) if full_history
                   else self.cfg.get("incremental_days", 6))
        pace = float(self.cfg.get("request_pace_s", 0.4))

        today = datetime.now().date()
        rows: dict[pd.Timestamp, dict[str, float]] = {}
        errors = 0
        for i in range(max(days, 1)):
            d = today - timedelta(days=i)
            ds = d.strftime("%Y%m%d")
            try:
                raw = ak.news_cctv(date=ds)
            except Exception as e:  # noqa: BLE001 — per-day isolation
                errors += 1
                log.debug("china_news %s failed: %s", ds, e)
                continue
            if raw is None or len(raw) == 0:
                continue   # weekend/holiday gap, not-yet-published, or pre-archive
            rows[pd.Timestamp(d)] = _tone_features(raw)
            if pace and i < days - 1:
                time.sleep(pace)

        if not rows:
            raise RuntimeError(
                f"china_news: no CCTV days fetched over {days}d window ({errors} errors)")
        out = pd.DataFrame.from_dict(rows, orient="index").sort_index()
        out.index.name = "date"
        log.info("china_news: %d/%d CCTV days fetched (%d errors)", len(rows), days, errors)
        return {"cctv_tone": out}
