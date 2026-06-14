"""San Francisco Fed collector — Daily News Sentiment Index.

The Daily News Sentiment Index (Buckman, Shapiro, Sudhof & Wilson) is a daily,
high-frequency measure of US economic sentiment from lexical analysis of major-
newspaper economics articles, history from 1980. It is a QUANT complement to the
engine's LLM news digests: a continuous, reproducible sentiment series that feeds
the conditions risk-appetite read (engine/conditions.py).

The Fed ships it as a small .xlsx with two sheets; the 'Data' sheet is
(date, News Sentiment). The download URL carries a cache-busting query string but
the base path is stable. See research/REAL_ACTIVITY_NOWCAST.md.
"""
from __future__ import annotations

import io

import pandas as pd

from collectors.base import Adapter
from lib import config


class NewsSentimentAdapter(Adapter):
    name = "frbsf_sentiment"
    group = "frbsf"
    stale_after_days = 10   # daily series, but a few business days' publication lag

    def __init__(self) -> None:
        self.cfg = config.load()["frbsf"]

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        r = self.http_get(self.cfg["news_sentiment_url"], retries=self.cfg["retries"],
                          timeout=90,
                          headers={"User-Agent": "Mozilla/5.0 (macro-dashboard research)"})
        return {"news_sentiment": self._parse(r.content)}

    @staticmethod
    def _parse(content: bytes) -> pd.DataFrame:
        xl = pd.ExcelFile(io.BytesIO(content))
        sheet = "Data" if "Data" in xl.sheet_names else xl.sheet_names[-1]
        df = xl.parse(sheet)
        cols = {str(c).lower().strip(): c for c in df.columns}
        dcol = cols.get("date")
        scol = next((orig for low, orig in cols.items() if "sentiment" in low), None)
        if dcol is None or scol is None:
            raise ValueError(f"unexpected news-sentiment columns: {list(df.columns)}")
        out = (df[[dcol, scol]]
               .rename(columns={dcol: "date", scol: "news_sentiment"}))
        out["news_sentiment"] = pd.to_numeric(out["news_sentiment"], errors="coerce")
        out["date"] = pd.to_datetime(out["date"], errors="coerce")
        return out.dropna(subset=["date"]).set_index("date").dropna()
