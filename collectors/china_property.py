"""China property + fiscal display layer — net-new free series for the
"China Property & Fiscal" regime card (proposal #10, scoped to DISPLAY/context).

All keyless, all on hosts the China dashboard already uses (Eastmoney datacenter
+ Sina futures). No akshare dependency — raw `requests`, same convention as
`collectors/china_macro.py`. Every series is independently wrapped so one broken
report can't kill the others; archived forever by store.upsert (the datacenter
only serves recent history).

Stored under group `china_property`, one parquet per series:
  home_price  70-city NBS new-/second-hand price diffusion (count rising − falling)
  climate     国房景气指数 (NBS real-estate climate composite — bundles the
              investment/sales/land cycle the fiddly YTD-cumulative prints carry,
              so we sidestep the Jan-Feb-combined de-cumulation gotcha entirely)
  cgb         China govt-bond curve (2/5/10/30y + 10y-2y slope) — the fiscal/duration
              read; the free LGFV-spread proxy alongside the property-ETF drawdown
  rebar       螺纹钢 continuous-main futures (construction-demand proxy, daily)
  iron_ore    铁矿石 continuous-main futures (the canonical China-growth barometer)

DISPLAY discipline: this is regime/context only — A-shares mean-revert and China
history is short, so none of this is fed into the scored china_axes (see
research/DATA_SIGNAL_EXPANSION_2026.md #10).
"""
from __future__ import annotations

import json
import logging

import pandas as pd

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")
_DC = "https://datacenter-web.eastmoney.com/api/data/v1/get"        # newer datacenter (v1)
_DC_LEGACY = "https://datacenter.eastmoney.com/api/data/get"        # token-style datacenter
_SINA = ("https://stock2.finance.sina.com.cn/futures/api/jsonp.php/"
         "var%20_x=/InnerFuturesNewService.getDailyKLine")
# the legacy datacenter needs the WEB token from Eastmoney's public page JS —
# read via EASTMONEY_WEB_TOKEN (env/.env) per CXI credential tripwire

TIER1 = {"北京", "上海", "广州", "深圳"}     # 一线城市 — the leadership cohort

# CGB curve field map (datacenter.eastmoney RPTA_WEB_TREASURYYIELD)
_CGB_FIELDS = {"cgb_2y": "EMM00588704", "cgb_5y": "EMM00166462",
               "cgb_10y": "EMM00166466", "cgb_30y": "EMM00166469",
               "cgb_10y2y": "EMM01276014"}
# Sina continuous-main contract symbols
_FUT = {"rebar": "RB0", "iron_ore": "I0"}


class ChinaPropertyAdapter(Adapter):
    name = "china_property"
    group = "china_property"
    stale_after_days = 12   # daily futures keep last_date current; monthly legs lag ~6wk

    def _headers(self) -> dict:
        return {"User-Agent": _UA, "Referer": "https://data.eastmoney.com/"}

    # -- 70-city home-price diffusion ----------------------------------------
    def _home_price(self, full_history: bool = False) -> pd.DataFrame:
        """All-70-city NBS price report → monthly diffusion (rising − falling).

        RPT_ECONOMY_HOUSE_PRICE carries every city (akshare's wrapper only filters
        two). FIRST/SECOND_COMHOUSE_SEQUENTIAL are the month-on-month price index
        where 100 = unchanged, so a city is 'rising' when > 100. Diffusion =
        count(>100) − count(<100). Rows arrive newest-month-first, so an incremental
        run reads the first few pages (recent months) and the ``cities >= 40`` guard
        below drops the page-boundary-truncated oldest month; a full run paginates
        every month back to 2011."""
        max_pages = 30 if full_history else 3        # 3 pages ≈ 21 recent months
        rows: list[dict] = []
        page_no = 1
        while page_no <= max_pages:
            params = {"reportName": "RPT_ECONOMY_HOUSE_PRICE",
                      "columns": ("REPORT_DATE,CITY,FIRST_COMHOUSE_SAME,FIRST_COMHOUSE_SEQUENTIAL,"
                                  "SECOND_HOUSE_SAME,SECOND_HOUSE_SEQUENTIAL"),
                      "pageSize": 500, "pageNumber": page_no,
                      "sortColumns": "REPORT_DATE,CITY", "sortTypes": "-1,-1"}
            r = self.http_get(_DC, params=params, retries=3, headers=self._headers(), timeout=30)
            result = (r.json() or {}).get("result") or {}
            data = result.get("data") or []
            rows.extend(data)
            if not data or page_no >= (result.get("pages") or 1):
                break
            page_no += 1
        if not rows:
            raise ValueError("home_price: empty result")
        raw = pd.DataFrame(rows)
        raw["month"] = pd.to_datetime(raw["REPORT_DATE"]).dt.normalize()
        for c in ("FIRST_COMHOUSE_SEQUENTIAL", "SECOND_HOUSE_SEQUENTIAL",
                  "FIRST_COMHOUSE_SAME", "SECOND_HOUSE_SAME"):
            raw[c] = pd.to_numeric(raw.get(c), errors="coerce")

        def agg(g: pd.DataFrame) -> pd.Series:
            seq, sec = g["FIRST_COMHOUSE_SEQUENTIAL"], g["SECOND_HOUSE_SEQUENTIAL"]
            t1 = g[g["CITY"].isin(TIER1)]
            return pd.Series({
                "new_rising": int((seq > 100).sum()), "new_falling": int((seq < 100).sum()),
                "new_flat": int((seq == 100).sum()),
                "new_breadth": int((seq > 100).sum() - (seq < 100).sum()),
                "second_breadth": int((sec > 100).sum() - (sec < 100).sum()),
                "cities": int(seq.notna().sum()),
                # tier-1 leadership: average MoM / YoY in percentage points (index − 100)
                "tier1_new_mom": round(float(t1["FIRST_COMHOUSE_SEQUENTIAL"].mean() - 100), 3)
                if not t1.empty else None,
                "tier1_new_yoy": round(float(t1["FIRST_COMHOUSE_SAME"].mean() - 100), 3)
                if not t1.empty else None,
            })

        out = raw.groupby("month", group_keys=False).apply(agg).sort_index()
        out = out[out["cities"] >= 40]    # drop any partial early month
        if out.empty:
            raise ValueError("home_price: no usable months")
        return out

    # -- NBS real-estate climate composite -----------------------------------
    def _climate(self) -> pd.DataFrame:
        """国房景气指数 (RPT_INDUSTRY_INDEX / EMM00121987) — the NBS real-estate
        climate composite. 100 = neutral; bundles investment/sales/land/funding."""
        params = {"reportName": "RPT_INDUSTRY_INDEX",
                  "columns": "REPORT_DATE,INDICATOR_VALUE,CHANGE_RATE",
                  "filter": '(INDICATOR_ID="EMM00121987")',
                  "pageSize": 1000, "pageNumber": 1,
                  "sortColumns": "REPORT_DATE", "sortTypes": "-1"}
        r = self.http_get(_DC, params=params, retries=3, headers=self._headers(), timeout=30)
        data = ((r.json() or {}).get("result") or {}).get("data") or []
        if not data:
            raise ValueError("climate: empty result")
        raw = pd.DataFrame(data)
        out = pd.DataFrame(index=pd.to_datetime(raw["REPORT_DATE"]))
        out["climate"] = pd.to_numeric(raw["INDICATOR_VALUE"], errors="coerce").to_numpy()
        out["climate_chg"] = pd.to_numeric(raw["CHANGE_RATE"], errors="coerce").to_numpy()
        out = out.dropna(how="all").sort_index()
        if out.empty:
            raise ValueError("climate: no usable rows")
        return out

    # -- China govt-bond curve (fiscal / duration read) ----------------------
    def _cgb(self, full_history: bool = False) -> pd.DataFrame:
        """CGB yields 2/5/10/30y + 10y-2y slope from the legacy token datacenter
        (RPTA_WEB_TREASURYYIELD) — JSON, no chinabond legacy-SSL scrape needed.
        Incremental runs read the newest page (~500 trading days, sorted desc);
        the store keeps the deep history a full run backfills to 2002."""
        token = config.secret("EASTMONEY_WEB_TOKEN")
        if not token:
            raise ValueError("cgb: EASTMONEY_WEB_TOKEN not set — series skipped")
        max_pages = 40 if full_history else 1
        rows: list[dict] = []
        page_no = 1
        while page_no <= max_pages:
            params = {"type": "RPTA_WEB_TREASURYYIELD", "sty": "ALL", "st": "SOLAR_DATE",
                      "sr": "-1", "token": token, "ps": 500,
                      "p": page_no, "pageNo": page_no, "pageNum": page_no}
            r = self.http_get(_DC_LEGACY, params=params, retries=3,
                              headers={"User-Agent": _UA}, timeout=30)
            result = (r.json() or {}).get("result") or {}
            data = result.get("data") or []
            rows.extend(data)
            if not data or page_no >= (result.get("pages") or 1):
                break
            page_no += 1
        if not rows:
            raise ValueError("cgb: empty result")
        raw = pd.DataFrame(rows)
        out = pd.DataFrame(index=pd.to_datetime(raw["SOLAR_DATE"]))
        for stored, src in _CGB_FIELDS.items():
            if src in raw.columns:
                out[stored] = pd.to_numeric(raw[src], errors="coerce").to_numpy()
        out = out.dropna(how="all").sort_index()
        if out.empty or "cgb_10y" not in out.columns:
            raise ValueError("cgb: no usable yields")
        return out

    # -- construction-demand futures (Sina) ----------------------------------
    def _futures(self, symbol: str) -> pd.DataFrame:
        """Continuous-main daily OHLC from Sina's JSONP kline endpoint."""
        r = self.http_get(_SINA, params={"symbol": symbol, "type": "2021_04_12"},
                          retries=3, headers={"User-Agent": _UA}, timeout=30)
        try:
            arr = json.loads(r.text.split("=(")[1].split(");")[0])
        except (IndexError, json.JSONDecodeError) as e:
            raise ValueError(f"{symbol}: unparseable Sina payload ({e})")
        if not arr:
            raise ValueError(f"{symbol}: empty kline")
        raw = pd.DataFrame(arr)
        out = pd.DataFrame(index=pd.to_datetime(raw["d"]))
        out["close"] = pd.to_numeric(raw["c"], errors="coerce").to_numpy()
        out["volume"] = pd.to_numeric(raw["v"], errors="coerce").to_numpy()
        out["hold"] = pd.to_numeric(raw["p"], errors="coerce").to_numpy()
        out = out.dropna(subset=["close"]).sort_index()
        if out.empty:
            raise ValueError(f"{symbol}: no usable rows")
        return out

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        frames: dict[str, pd.DataFrame] = {}
        errors: list[str] = []
        jobs = [("home_price", lambda: self._home_price(full_history)),
                ("climate", self._climate),
                ("cgb", lambda: self._cgb(full_history))]
        jobs += [(name, lambda s=sym: self._futures(s)) for name, sym in _FUT.items()]
        for key, fn in jobs:
            try:
                frames[key] = fn()
            except Exception as e:  # noqa: BLE001 — per-series isolation
                errors.append(f"{key}: {e}")
                log.warning("china_property series %s failed: %s", key, e)
        if not frames:
            raise RuntimeError("china_property: all series failed — " + " | ".join(errors))
        if errors:
            log.info("china_property: %d/%d series ok (skipped: %s)",
                     len(frames), len(frames) + len(errors), "; ".join(errors))
        return frames
