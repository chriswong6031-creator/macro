"""FRED collector.

Two paths:
- Official API (api.stlouisfed.org) when FRED_API_KEY is set — full history,
  reliable. Preferred in CI.
- Keyless fredgraph.csv fallback — same data, but the endpoint is flaky
  (occasional 504s), hence aggressive retries.

OAS caveat: since April 2026 FRED serves only a rolling 3-year window for the
ICE BofA OAS series (BAMLH0A0HYM2, BAMLC0A0CM). The store's upsert is
append-only, so every observation we ever see is kept permanently. Pre-window
history lives in data/archive/ (see DECISIONS.md for provenance).
"""
from __future__ import annotations

import io

import pandas as pd

from collectors.base import Adapter
from lib import config


class FredAdapter(Adapter):
    name = "fred"
    group = "fred"

    def __init__(self) -> None:
        self.cfg = config.load()["fred"]
        self.api_key = config.secret("FRED_API_KEY")

    def _all_series(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for grp in self.cfg["series"].values():
            out.update(grp)
        return out

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        frames: dict[str, pd.DataFrame] = {}
        errors: list[str] = []
        for sid, col in self._all_series().items():
            try:
                frames[sid] = self._fetch_one(sid, col)
            except Exception as e:  # noqa: BLE001 — partial success allowed
                errors.append(f"{sid}: {e}")
        if not frames:
            raise RuntimeError(f"all FRED series failed: {errors}")
        if errors:
            # surfaced via logs; missing series simply stay at last stored date
            import logging
            logging.getLogger(__name__).warning("FRED partial failure: %s", errors)
        return frames

    def _fetch_one(self, sid: str, col: str) -> pd.DataFrame:
        if self.api_key:
            return self._fetch_api(sid, col)
        return self._fetch_csv(sid, col)

    def _fetch_api(self, sid: str, col: str) -> pd.DataFrame:
        r = self.http_get(
            self.cfg["api_url"],
            retries=self.cfg["retries"],
            backoff_base=self.cfg["backoff_base_s"],
            params={"series_id": sid, "api_key": self.api_key,
                    "file_type": "json", "limit": 100000},
        )
        obs = r.json()["observations"]
        df = pd.DataFrame(obs)[["date", "value"]]
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df = df.set_index("date").rename(columns={"value": col})
        return df.dropna()

    def _fetch_csv(self, sid: str, col: str) -> pd.DataFrame:
        r = self.http_get(
            f"{self.cfg['csv_url']}?id={sid}",
            retries=self.cfg["retries"],
            backoff_base=self.cfg["backoff_base_s"],
            timeout=90,
        )
        df = pd.read_csv(io.StringIO(r.text))
        if df.shape[1] != 2 or "observation_date" not in df.columns[0].lower().replace(" ", "_"):
            # fredgraph returns an HTML error page on failure; first col header
            # is normally 'observation_date' (legacy 'DATE')
            if df.columns[0].upper() not in ("DATE", "OBSERVATION_DATE"):
                raise ValueError(f"unexpected fredgraph response for {sid}: cols={list(df.columns)}")
        df.columns = ["date", col]
        df[col] = pd.to_numeric(df[col], errors="coerce")
        return df.set_index("date").dropna()
