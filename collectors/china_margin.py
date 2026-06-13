"""China margin financing (融资融券) — the A-share "crowd meter / positioning" plane.

Two Eastmoney datacenter reports (keyless JSON, live-verified 2026-06-13), the
cleanest free analog to the US CFTC-COT positioning panel:

  balance      RPTA_RZRQ_LSHJ            whole-market margin balance, daily 2010-03->
               financing balance, financing-as-%-of-float (RZYEZB, self-normalizing
               so it can be percentile-ranked like net-spec positioning: ~4.7% at the
               2015 leverage-bubble peak vs ~2.8% today), daily net financing buy.
  daily_trade  RPTA_WEB_MARGIN_DAILYTRADE  margin-account stats, daily 2012-09->
               average maintenance ratio (distance-to-margin-call), margin-trades-
               as-%-of-turnover (froth share), investors carrying margin debt.

Same scraper discipline as collectors/china_macro.py: browser UA + Referer, per-series
isolation, archive-forever via store.upsert (the datacenter only serves recent pages).
Balances are normalised to 亿元 (hundred-million yuan) so the two reports co-plot.
"""
from __future__ import annotations

import logging

import pandas as pd

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")
_BASE = "https://datacenter-web.eastmoney.com/api/data/v1/get"
_REFERER = "https://data.eastmoney.com/"
_YI = 1e8  # 亿 — raw-yuan reports are divided by this; 亿-native reports are not

# report -> (date_field, {stored_col: (source_field, scale)}) — scale 1/_YI for raw yuan
_REPORTS = {
    "balance": ("RPTA_RZRQ_LSHJ", "DIM_DATE", {
        "margin_total":  ("RZRQYE", _YI),   # total margin balance (financing + sec-lending)
        "fin_balance":   ("RZYE", _YI),     # financing balance
        "fin_pct_float": ("RZYEZB", 1.0),   # financing as % of float mktcap (self-normalizing)
        "net_fin_buy":   ("RZJME", _YI),    # daily net financing buy (accumulation/distribution)
        "sec_lending":   ("RQYE", _YI),     # securities-lending balance
    }),
    "daily_trade": ("RPTA_WEB_MARGIN_DAILYTRADE", "STATISTICS_DATE", {
        "margin_balance":  ("MARGIN_BALANCE", 1.0),        # already 亿元
        "balance_ratio":   ("BALANCE_RATIO", 1.0),         # % of float
        "margin_trade_amt": ("MARGIN_TRADE_AMT", 1.0),     # margin trade value 亿元 (÷ratio ⇒ whole-market turnover)
        "trade_amt_ratio": ("TRADE_AMT_RATIO", 1.0),       # margin trades as % of turnover (froth)
        "guarantee_ratio": ("AVG_GUARANTEE_RATIO", 1.0),   # avg maintenance ratio (margin-call distance)
        "liab_investors":  ("MARGINLIAB_INVESTOR_NUM", 1.0),  # investors carrying margin debt
    }),
}


class ChinaMarginAdapter(Adapter):
    name = "china_margin"
    group = "china_margin"
    stale_after_days = 6   # daily T+0 evening release; allow a long weekend

    def __init__(self) -> None:
        self.retries = 3

    def _headers(self) -> dict:
        return {"User-Agent": _UA, "Referer": _REFERER}

    def _paged(self, report: str, sort_col: str, full_history: bool) -> pd.DataFrame:
        """Walk datacenter pages newest-first until we have enough rows. Daily runs
        only need the recent tail (history is archived); full runs page to the end."""
        page_size = 2000 if full_history else 90
        max_pages = 6 if full_history else 1
        rows: list[dict] = []
        for page_no in range(1, max_pages + 1):
            params = {"reportName": report, "columns": "ALL", "pageSize": page_size,
                      "sortColumns": sort_col, "sortTypes": -1, "pageNumber": page_no}
            r = self.http_get(_BASE, params=params, retries=self.retries,
                              headers=self._headers(), timeout=30)
            res = (r.json() or {}).get("result") or {}
            data = res.get("data") or []
            rows.extend(data)
            pages = res.get("pages") or 1
            if not data or page_no >= pages:
                break
        if not rows:
            raise ValueError(f"{report}: empty result")
        return pd.DataFrame(rows)

    def _series(self, key: str, full_history: bool) -> pd.DataFrame:
        report, date_col, fields = _REPORTS[key]
        raw = self._paged(report, date_col, full_history)
        idx = pd.to_datetime(raw[date_col])
        out = pd.DataFrame(index=idx)
        for stored, (src, scale) in fields.items():
            if src in raw.columns:
                # assign by value — raw carries a RangeIndex that would otherwise
                # align to NaN against the DatetimeIndex (same gotcha as china_macro)
                col = pd.to_numeric(raw[src], errors="coerce").to_numpy()
                out[stored] = col / scale if scale != 1.0 else col
        out = out.dropna(how="all").sort_index()
        if out.empty:
            raise ValueError(f"{report}: no usable columns")
        return out

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        frames: dict[str, pd.DataFrame] = {}
        errors: list[str] = []
        for key in _REPORTS:
            try:
                frames[key] = self._series(key, full_history)
            except Exception as e:  # noqa: BLE001 — per-series isolation
                errors.append(f"{key}: {e}")
                log.warning("china_margin series %s failed: %s", key, e)
        if not frames:
            raise RuntimeError("china_margin: all series failed — " + " | ".join(errors))
        if errors:
            log.info("china_margin: %d/%d series ok (skipped: %s)",
                     len(frames), len(frames) + len(errors), "; ".join(errors))
        return frames
