"""China high-frequency sentiment/flow snapshots — A-share-native gauges with no
free deep history, so they accrue forward (archived via store.upsert):

  ah_premium    Hang Seng A/H premium index (恒生沪深港通AH股溢价指数). >100 = mainland
                A-shares richer than their HK twins; mean-reverting cross-market
                risk-appetite gauge. Backfilled from push2his klines when reachable,
                else a daily Sina snapshot (hq.sinajs.cn, GBK).
  limit_breadth limit-up / limit-down / broken-board counts (涨停/跌停/炸板家数) and the
                seal rate ZT/(ZT+ZB). The best high-frequency A-share speculation
                thermometer. push2ex retains only ~2 weeks, so we seed a short backfill
                and append daily (NOT deeply backfillable — every missed day is lost).
  etf_shares    total shares outstanding of the tracked broad+sector ETF basket
                (RPT_FUND_ETFLIST DEC_TOTALSHARE). Differenced downstream into a
                creations/redemptions flow proxy (institutional/national-team tell).
                Live snapshot only (no date field) -> append daily.

All three degrade independently; a blocked source just leaves its parquet to grow
from the next good day.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

import pandas as pd

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")
_PUSH2EX = "https://push2ex.eastmoney.com/"
_PUSH2HIS = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
_DC = "https://datacenter-web.eastmoney.com/api/data/v1/get"
# push2ex needs the ut token from Eastmoney's public page JS — read via
# EASTMONEY_UT_TOKEN (env/.env), same class as the CXI credential tripwire


class ChinaFlowsAdapter(Adapter):
    name = "china_flows"
    group = "china_flows"
    stale_after_days = 6

    def __init__(self) -> None:
        cfg = config.load()["china"]["yahoo"]
        # bare codes (no .SS/.SZ) for the ETF fund list — broad + sector ETFs only
        codes = list(cfg["indices"].keys()) + list(cfg["sector_etfs"].keys())
        self.etf_codes = sorted({c.split(".")[0] for c in codes if c[0].isdigit()})

    def _h(self, referer: str) -> dict:
        return {"User-Agent": _UA, "Referer": referer}

    # -- AH premium ------------------------------------------------------------
    def _ah_premium(self, full_history: bool) -> pd.DataFrame:
        # try the push2his kline backfill first (gives real history if reachable)
        if full_history:
            try:
                params = {"secid": "100.HSAHP", "fields1": "f1,f2", "fields2": "f51,f53",
                          "klt": 101, "fqt": 0, "lmt": 5000, "end": "20500101"}
                r = self.http_get(_PUSH2HIS, params=params, retries=2,
                                  headers=self._h("https://quote.eastmoney.com/"), timeout=25)
                kl = (((r.json() or {}).get("data") or {}).get("klines")) or []
                recs = {}
                for row in kl:
                    p = str(row).split(",")
                    if len(p) >= 2:
                        try:
                            recs[pd.to_datetime(p[0])] = float(p[1])
                        except ValueError:
                            pass
                if recs:
                    return pd.DataFrame({"hsahp": pd.Series(recs)}).sort_index()
            except Exception as e:  # noqa: BLE001 — fall through to the snapshot
                log.info("china_flows ah_premium kline backfill failed (%s); snapshot only", e)
        # daily Sina snapshot (GBK): var hq_str_znb_HSAHP="name,LEVEL,...,DATE,TIME,...";
        r = self.http_get("https://hq.sinajs.cn/list=znb_HSAHP", retries=2,
                          headers=self._h("https://finance.sina.com.cn/"), timeout=20)
        txt = r.content.decode("gbk", errors="replace")
        body = txt.split('"', 1)[1].rsplit('"', 1)[0] if '"' in txt else ""
        parts = body.split(",")
        if len(parts) < 7:
            raise ValueError("ah_premium: unparseable Sina payload")
        level = float(parts[1])
        when = pd.to_datetime(parts[6]) if parts[6] else pd.Timestamp(date.today())
        return pd.DataFrame({"hsahp": [level]}, index=[when])

    # -- limit-up / down / broken-board breadth --------------------------------
    def _pool_count(self, pool: str, yyyymmdd: str, ut: str) -> int | None:
        params = {"ut": ut, "dpt": "wz.ztzt", "Pageindex": 0, "pagesize": 5,
                  "sort": "fbt:asc", "date": yyyymmdd}
        try:
            r = self.http_get(_PUSH2EX + pool, params=params, retries=2,
                              headers=self._h("https://quote.eastmoney.com/"), timeout=20)
            d = (r.json() or {}).get("data")
            if isinstance(d, dict):
                return int(d.get("tc") or 0)
        except Exception as e:  # noqa: BLE001
            log.debug("china_flows pool %s %s failed: %s", pool, yyyymmdd, e)
        return None

    def _limit_breadth(self, full_history: bool) -> pd.DataFrame:
        ut = config.secret("EASTMONEY_UT_TOKEN")
        if not ut:
            # every missed day is unrecoverable (~2wk retention) — fail the leg loudly
            raise ValueError("limit_breadth: EASTMONEY_UT_TOKEN not set — leg skipped")
        # push2ex keeps ~2 weeks; seed a short backfill, then append daily
        ndays = 18 if full_history else 4
        rows = {}
        for back in range(ndays):
            d = date.today() - timedelta(days=back)
            if d.weekday() >= 5:   # skip weekends (A-shares closed)
                continue
            ymd = d.strftime("%Y%m%d")
            zt = self._pool_count("getTopicZTPool", ymd, ut)
            if zt is None:   # non-trading day or out of retention window
                continue
            dt = self._pool_count("getTopicDTPool", ymd, ut) or 0
            zb = self._pool_count("getTopicZBPool", ymd, ut) or 0
            seal = round(100 * zt / (zt + zb), 2) if (zt + zb) else None
            rows[pd.to_datetime(d)] = {"zt": zt, "dt": dt, "zb": zb, "seal_rate": seal}
        if not rows:
            raise ValueError("limit_breadth: no pool data in window")
        return pd.DataFrame.from_dict(rows, orient="index").sort_index()

    # -- ETF shares outstanding (flow proxy) -----------------------------------
    def _etf_shares(self, full_history: bool) -> pd.DataFrame:
        flt = "(SECURITY_CODE in (" + ",".join(f'"{c}"' for c in self.etf_codes) + "))"
        params = {"reportName": "RPT_FUND_ETFLIST", "columns": "SECURITY_CODE,DEC_TOTALSHARE",
                  "pageSize": 200, "pageNumber": 1, "filter": flt}
        r = self.http_get(_DC, params=params, retries=2,
                          headers=self._h("https://data.eastmoney.com/"), timeout=25)
        data = ((r.json() or {}).get("result") or {}).get("data") or []
        if not data:
            raise ValueError("etf_shares: empty result")
        row = {f"sh_{d['SECURITY_CODE']}": pd.to_numeric(d.get("DEC_TOTALSHARE"), errors="coerce")
               for d in data if d.get("SECURITY_CODE")}
        return pd.DataFrame(row, index=[pd.Timestamp(date.today())])

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        frames: dict[str, pd.DataFrame] = {}
        errors: list[str] = []
        for key, fn in (("ah_premium", self._ah_premium),
                        ("limit_breadth", self._limit_breadth),
                        ("etf_shares", self._etf_shares)):
            try:
                frames[key] = fn(full_history)
            except Exception as e:  # noqa: BLE001 — per-series isolation
                errors.append(f"{key}: {e}")
                log.warning("china_flows %s failed: %s", key, e)
        if not frames:
            raise RuntimeError("china_flows: all series failed — " + " | ".join(errors))
        if errors:
            log.info("china_flows: %d/%d series ok (skipped: %s)",
                     len(frames), len(frames) + len(errors), "; ".join(errors))
        return frames
