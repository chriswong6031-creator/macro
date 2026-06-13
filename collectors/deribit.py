"""Deribit public API collector (free, keyless).

- dvol: BTC implied-volatility index, daily OHLC since ~Mar 2021 (verified:
  2019 queries return empty). Chunked yearly requests handle the API's
  per-call point limits.
- options_summary: ONE call returns every listed BTC option (~950 instruments)
  with open_interest + mark_iv -> daily snapshot row: total OI, put/call OI
  ratio, OI-weighted mark IV. (Term-structure/skew panels can be derived later
  from the same call; we store the aggregates the Vector build needs.)
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pandas as pd

from collectors.base import Adapter
from lib import config, store


class DeribitAdapter(Adapter):
    name = "deribit"
    group = "deribit"
    stale_after_days = 3

    def __init__(self) -> None:
        self.cfg = config.load()["deribit"]

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        out = {}
        dv = self._dvol(full_history)
        if dv is not None:
            out["dvol"] = dv
        opt = self._options_summary()
        if opt is not None:
            out["options_summary"] = opt
        if not out:
            raise ValueError("deribit returned nothing")
        return out

    def _dvol(self, full_history: bool) -> pd.DataFrame | None:
        last = store.last_date(self.group, "dvol")
        if full_history or last is None:
            start = date.fromisoformat(self.cfg["dvol_earliest"])
        else:
            start = last - timedelta(days=3)
        end = date.today()
        frames = []
        cursor = start
        while cursor <= end:
            chunk_end = min(cursor + timedelta(days=365), end)
            r = self.http_get(
                self.cfg["dvol_url"], retries=self.cfg["retries"],
                params={"currency": "BTC", "resolution": "86400",
                        "start_timestamp": str(int(datetime(cursor.year, cursor.month, cursor.day,
                                                            tzinfo=timezone.utc).timestamp() * 1000)),
                        "end_timestamp": str(int(datetime(chunk_end.year, chunk_end.month, chunk_end.day,
                                                          23, 59, tzinfo=timezone.utc).timestamp() * 1000))},
                timeout=30)
            data = (r.json().get("result") or {}).get("data") or []
            if data:
                df = pd.DataFrame(data, columns=["ts", "open", "high", "low", "close"])
                frames.append(df)
            cursor = chunk_end + timedelta(days=1)
        if not frames:
            return None
        allf = pd.concat(frames, ignore_index=True)
        allf["date"] = pd.to_datetime(allf["ts"], unit="ms").dt.normalize()
        allf = allf.set_index("date").sort_index()
        allf = allf[~allf.index.duplicated(keep="last")]
        return allf[["open", "high", "low", "close"]].rename(
            columns={c: f"dvol_{c}" for c in ["open", "high", "low", "close"]})

    def _options_summary(self) -> pd.DataFrame | None:
        r = self.http_get(self.cfg["options_url"], retries=self.cfg["retries"],
                          params={"currency": "BTC", "kind": "option"}, timeout=60)
        rows = r.json().get("result") or []
        if not rows:
            return None
        df = pd.DataFrame(rows)
        df["open_interest"] = pd.to_numeric(df["open_interest"], errors="coerce").fillna(0.0)
        df["mark_iv"] = pd.to_numeric(df.get("mark_iv"), errors="coerce")
        is_put = df["instrument_name"].str.endswith("-P")
        put_oi = float(df.loc[is_put, "open_interest"].sum())
        call_oi = float(df.loc[~is_put, "open_interest"].sum())
        w = df["open_interest"].where(df["mark_iv"].notna(), 0.0)
        iv_w = float((df["mark_iv"].fillna(0) * w).sum() / w.sum()) if w.sum() > 0 else None
        today = pd.Timestamp(datetime.now(timezone.utc).date())
        return pd.DataFrame({
            "options_oi_btc": [put_oi + call_oi],
            "put_call_oi_ratio": [put_oi / call_oi if call_oi else None],
            "iv_oi_weighted": [iv_w],
        }, index=[today])
