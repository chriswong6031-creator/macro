"""Hugging Face Hub model-download collector — the AI-adoption blind spot.

For the AI themes the real non-price signal is developer/model ADOPTION, which neither Quiver
nor federal money can see. The HF Hub API exposes each model's trailing-30-day `downloads`
(api keyless in practice; HF_TOKEN optional). This sums the top models per curated author org,
maps the org to a ticker (data/huggingface/author_ticker.json), and stores a daily SNAPSHOT so
the engine can derive download VELOCITY (the level alone is not a signal — a rising 30-day
download rate vs the cross-section is).

Output: data/huggingface/downloads.parquet — append-only daily snapshots
(ticker, downloads_30d, n_models, snapshot_date, _first_seen). Feeds the per-ticker convergence
kernel (hf_model_momentum channel). Display / context only — lowest-tier weight.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone

import pandas as pd

from collectors.base import Adapter, is_connection_error
from lib import config

log = logging.getLogger(__name__)

MODELS_URL = "https://huggingface.co/api/models"
TOP_N = 25       # top models per author by downloads (the long tail is noise)
PACE_S = 0.25


def _author_map() -> dict[str, list[str]]:
    p = config.data_dir() / "huggingface" / "author_ticker.json"
    if not p.exists():
        return {}
    try:
        return (json.loads(p.read_text()) or {}).get("authors", {})
    except Exception:  # noqa: BLE001
        return {}


class HuggingFaceAdapter(Adapter):
    name = "huggingface"
    group = "huggingface"
    stale_after_days = 3

    def __init__(self) -> None:
        self.token = config.secret("HF_TOKEN")  # optional — anon tier is plenty

    def _table_path(self):
        p = config.data_dir() / "huggingface" / "downloads.parquet"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def _author_downloads(self, author: str) -> tuple[float, int]:
        headers = {"User-Agent": config.load()["sponsors"]["user_agent"]}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        r = self.http_get(MODELS_URL, params={"author": author, "sort": "downloads", "limit": TOP_N},
                          retries=3, timeout=40, headers=headers)
        models = r.json() or []
        total = float(sum((m.get("downloads") or 0) for m in models))
        return total, len(models)

    def _merge(self, new: pd.DataFrame) -> pd.DataFrame:
        new = new.copy()
        new["_first_seen"] = datetime.now(timezone.utc).isoformat()
        path = self._table_path()
        if path.exists():
            combined = pd.concat([pd.read_parquet(path), new], ignore_index=True)
        else:
            combined = new
        # one snapshot per (ticker, snapshot_date) — re-runs same day don't double-count
        combined = combined.drop_duplicates(subset=["ticker", "snapshot_date"], keep="last").reset_index(drop=True)
        combined.to_parquet(path)
        return combined

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        amap = _author_map()
        if not amap:
            raise ValueError("huggingface: author_ticker.json missing or empty")
        today = datetime.now(timezone.utc).date().isoformat()
        rows, errors = [], 0
        for ticker, authors in amap.items():
            dl, nmod = 0.0, 0
            for author in authors:
                try:
                    d, n = self._author_downloads(author)
                    dl += d
                    nmod += n
                    time.sleep(PACE_S)
                except Exception as e:  # noqa: BLE001
                    if is_connection_error(e):
                        raise
                    errors += 1
                    log.debug("huggingface %s/%s: %s", ticker, author, e)
                    continue
            if nmod > 0:
                rows.append({"ticker": ticker, "downloads_30d": round(dl, 0),
                             "n_models": nmod, "snapshot_date": today})

        if not rows:
            raise RuntimeError(f"huggingface: no author returned models (errors={errors})")
        merged = self._merge(pd.DataFrame(rows))
        log.info("huggingface: %d tickers snapshot @ %s, %d total rows, %d errors",
                 len(rows), today, len(merged), errors)
        ingest = pd.DataFrame({"tickers": [len(rows)], "total_rows": [len(merged)]},
                              index=[pd.Timestamp(today)])
        return {"huggingface__ingest": ingest}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    HuggingFaceAdapter().fetch()
