"""Stock Connect flows (沪深港通) — repairs the broken connect_flow panel.

The repo's old data/china_macro/connect_flow.parquet (written by china_macro via
push2his kamt.kline) is DEAD: northbound_cum is frozen at a constant placeholder and
southbound_cum is entirely NaN (the kamt path no longer serves usable legs). This
collector replaces it with the Eastmoney datacenter history report (keyless JSON,
live-verified 2026-06-13), which still serves a clean daily series:

  southbound (MUTUAL_TYPE 006)  mainland buying Hong Kong — FULLY LIVE daily net,
                                buy/sell, turnover, and cumulative mainland-in-HK
                                holdings. A direct mainland risk-on/off gauge.
  northbound (MUTUAL_TYPE 005)  foreign buying A-shares — daily NET disclosure was
                                curtailed by regulators Aug-2024 (recent rows null);
                                historical net (pre-2024-08) + turnover are kept for
                                context and labeled "direction discontinued".

Stored under group `china_connect`. Net flow is consumed downstream as a z-score /
rolling cumulative (scale-invariant), so the raw source units are non-load-bearing.
"""
from __future__ import annotations

import logging

import pandas as pd

from collectors.base import Adapter

log = logging.getLogger(__name__)

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")
_BASE = "https://datacenter-web.eastmoney.com/api/data/v1/get"
_REFERER = "https://data.eastmoney.com/"
_YI = 1e8

# series -> MUTUAL_TYPE (combined legs: 005 north, 006 south)
_LEGS = {"southbound": "006", "northbound": "005"}
# stored_col -> (source_field, scale)
_FIELDS = {
    "net":         ("NET_DEAL_AMT", 1.0),     # daily net (buy - sell); z-scored downstream
    "buy":         ("BUY_AMT", 1.0),
    "sell":        ("SELL_AMT", 1.0),
    "turnover":    ("DEAL_AMT", 1.0),
    "hold_mktcap": ("HOLD_MARKET_CAP", _YI),  # cumulative holdings, normalised to 亿元
}


class ChinaConnectAdapter(Adapter):
    name = "china_connect"
    group = "china_connect"
    stale_after_days = 6   # daily; northbound may be permanently null going forward

    def __init__(self) -> None:
        self.retries = 3

    def _headers(self) -> dict:
        return {"User-Agent": _UA, "Referer": _REFERER}

    def _leg(self, mutual_type: str, full_history: bool) -> pd.DataFrame:
        page_size = 4000 if full_history else 90
        params = {"reportName": "RPT_MUTUAL_DEAL_HISTORY", "columns": "ALL",
                  "pageSize": page_size, "sortColumns": "TRADE_DATE", "sortTypes": -1,
                  "pageNumber": 1, "filter": f'(MUTUAL_TYPE="{mutual_type}")'}
        r = self.http_get(_BASE, params=params, retries=self.retries,
                          headers=self._headers(), timeout=30)
        data = ((r.json() or {}).get("result") or {}).get("data") or []
        if not data:
            raise ValueError(f"type {mutual_type}: empty result")
        raw = pd.DataFrame(data)
        idx = pd.to_datetime(raw["TRADE_DATE"])
        out = pd.DataFrame(index=idx)
        for stored, (src, scale) in _FIELDS.items():
            if src in raw.columns:
                col = pd.to_numeric(raw[src], errors="coerce").to_numpy()
                out[stored] = col / scale if scale != 1.0 else col
        out = out.dropna(how="all").sort_index()
        if out.empty:
            raise ValueError(f"type {mutual_type}: no usable rows")
        return out

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        frames: dict[str, pd.DataFrame] = {}
        errors: list[str] = []
        for name, mtype in _LEGS.items():
            try:
                frames[name] = self._leg(mtype, full_history)
            except Exception as e:  # noqa: BLE001 — northbound may legitimately be empty now
                errors.append(f"{name}: {e}")
                log.warning("china_connect %s failed: %s", name, e)
        if not frames:
            raise RuntimeError("china_connect: all legs failed — " + " | ".join(errors))
        if errors:
            log.info("china_connect: %d/%d legs ok (skipped: %s)",
                     len(frames), len(frames) + len(errors), "; ".join(errors))
        return frames
