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
  etf_shares    shares outstanding (份) of the FULL official exchange ETF universe:
                the SSE commonQuery ETF-规模 table (~880 funds, dated by STAT_DATE,
                TOT_VOL quoted in 万份) unioned with the SZSE fund xlsx (~700 ETF rows
                of 1013, 当前规模(份) already raw 份). Native exchange transport per
                CNH-R2; the legacy 21-code EastMoney RPT_FUND_ETFLIST basket survives
                as the documented LAST-RESORT fallback. Differenced downstream into a
                creations/redemptions flow proxy (institutional/national-team tell).
                Daily snapshots only (no deep history published) -> append daily.

All three degrade independently; a blocked source just leaves its parquet to grow
from the next good day.

etf_shares DATING SEAM (one-time, W2 widening)
----------------------------------------------
Legacy rows were stamped at the COLLECTION date, which is the official STAT_DATE + 1
session (the nightly ran after the exchange published the prior close). New rows carry
the official STAT_DATE itself, so on the switchover day the basis is re-dated one
session EARLIER. That is a one-time, <=1-session distortion inside the participation
engine's 5d rolling z (engine/china_participation.py::_load_etf_flows), accepted in
exchange for honest PIT dating from here on. The 21 legacy codes are all inside the new
universe, so the cross-fund median z stays non-null across the seam: the ~1,560 newly
added funds are simply NaN on pre-seam rows and contribute nothing until they have two
diffs of their own.
"""
from __future__ import annotations

import io
import logging
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

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

# -- official ETF-universe endpoints (etf_shares leg) -------------------------
_SSE_COMMON_QUERY = "https://query.sse.com.cn/commonQuery.do"
_SSE_ETF_SCALE_SQLID = "COMMON_SSE_ZQPZ_ETFZL_XXPL_ETFGM_SEARCH_L"
_SZSE_FUND_REPORT = "https://fund.szse.cn/api/report/ShowReport"

_SSE_WALKBACK_DAYS = 4      # STAT_DATE candidates tried, newest first
_HOST_THROTTLE_S = 1.0      # <=1 req/s/host — the SSE walk-back sleeps between calls
_WAN = 10_000.0             # 万 -> unit multiplier for SSE TOT_VOL (万份 -> 份)
# Sanity floor on the merged universe. A partial pull (one exchange half-answering, a
# truncated page) would drop hundreds of funds to NaN and poison the per-fund 5d z-scores
# downstream with mass NaN churn, so anything thinner is treated as a broken pull and
# falls through to the EastMoney fallback instead. Module-level so tests can relax it.
_MIN_UNIVERSE_COLS = 200


def _today_cn() -> date:
    """Today in exchange local time (Asia/Shanghai). Module-level for test override."""
    return datetime.now(ZoneInfo("Asia/Shanghai")).date()


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
    #
    # UNIT CONTINUITY — the seam must not move the basis (verified live 2026-07-25/26).
    # The legacy EastMoney DEC_TOTALSHARE basis is raw 份, and both official legs are
    # normalised into raw 份 as well:
    #   SSE  TOT_VOL is quoted in 万份, so it needs x10000:
    #        stored sh_510300 = 24,380,587,700 份
    #             == SSE TOT_VOL 2,438,058.77 万份 x 10000.  Exact match.
    #   SZSE 当前规模(份) is ALREADY raw 份, as a comma-grouped string, so it is used
    #        as-is after stripping the commas:
    #        stored sh_159915 = 16,619,454,936 vs xlsx "16,653,454,936" — same order of
    #        magnitude and same unit; the 34m delta is the T-vs-T-1 attribution gap
    #        (the xlsx is an undated snapshot), NOT a unit error.
    # The x10000 product is rounded to whole 份: SSE quotes to 0.01 万份 = 100 份, so the
    # true value is always integral, and a bare binary multiply leaves artefacts
    # (744,006.68 x 1e4 -> 7440066800.000001) that would show up as phantom 1-unit
    # creations in the downstream diff.
    def _cn_weekdays_back(self, n: int) -> list[date]:
        """The *n* most recent CN weekdays counting back from today, TODAY-INCLUSIVE.

        Today-inclusive on purpose: the asia collect lane runs after the A-share close,
        so the exchange has usually already published the same session. A yesterday-first
        walk would permanently lag the store one session behind the published data.
        """
        out: list[date] = []
        d = _today_cn()
        while len(out) < n:
            if d.weekday() < 5:       # A-shares closed Sat/Sun
                out.append(d)
            d -= timedelta(days=1)
        return out

    def _etf_shares_sse(self) -> tuple[dict[str, float], pd.Timestamp]:
        """Full SSE ETF universe (~880 funds) at the newest PUBLISHED STAT_DATE.

        commonQuery answers an empty ``result`` list for a non-trading or not-yet-published
        date, so we walk back over the most recent weekdays and take the first non-empty
        answer — sleeping between successive calls to hold <=1 req/s on query.sse.com.cn.
        Returns ({sh_<code>: 份}, as_of) where as_of is the exchange's own STAT_DATE.
        """
        errors: list[str] = []
        for i, d in enumerate(self._cn_weekdays_back(_SSE_WALKBACK_DAYS)):
            if i:
                time.sleep(_HOST_THROTTLE_S)
            stat_date = d.isoformat()
            params = {"isPagination": "true", "pageHelp.pageSize": 10000,
                      "pageHelp.pageNo": 1, "pageHelp.beginPage": 1,
                      "pageHelp.cacheSize": 1, "pageHelp.endPage": 1,
                      "sqlId": _SSE_ETF_SCALE_SQLID, "STAT_DATE": stat_date}
            try:
                r = self.http_get(_SSE_COMMON_QUERY, params=params, retries=2,
                                  headers=self._h("https://www.sse.com.cn/"), timeout=25)
                rows = (r.json() or {}).get("result") or []
            except Exception as e:  # noqa: BLE001 — try the next candidate date
                errors.append(f"{stat_date}: {e}")
                continue
            out: dict[str, float] = {}
            for row in rows:
                code = str(row.get("SEC_CODE") or "").strip()
                vol = pd.to_numeric(
                    str(row.get("TOT_VOL") or "").replace(",", "").strip(), errors="coerce")
                if code and pd.notna(vol):
                    out[f"sh_{code}"] = float(round(float(vol) * _WAN))   # 万份 -> 份
            if not out:
                continue              # non-trading day / not yet published
            # Prefer the STAT_DATE the exchange stamped on the rows over the one we asked
            # for, so a server that ignores the filter still dates the row honestly.
            echoed = max((str(row.get("STAT_DATE") or "").strip() for row in rows),
                         default="")
            try:
                as_of = pd.Timestamp(echoed) if echoed else pd.Timestamp(d)
            except ValueError:
                as_of = pd.Timestamp(d)
            log.info("china_flows etf_shares: SSE %d funds at STAT_DATE %s",
                     len(out), as_of.date())
            return out, as_of
        raise ValueError("etf_shares SSE: no published STAT_DATE in the last "
                         f"{_SSE_WALKBACK_DAYS} weekdays"
                         + (f" ({'; '.join(errors)})" if errors else ""))

    def _etf_shares_szse(self) -> dict[str, float]:
        """Full SZSE ETF universe from the fund xlsx (~700 ETF rows of 1013).

        The xlsx carries NO date column — it is a live snapshot — so the caller stamps it
        with the STAT_DATE the SSE leg resolved.  That means SZSE values can be attributed
        up to one session off (the SZSE snapshot is "now", the SSE table is the published
        close); accepted, because a per-fund 5d z-score is insensitive to a uniform
        <=1-session shift and the alternative (a second, differently-dated store) would
        break the single-frame consumer contract.
        """
        r = self.http_get(_SZSE_FUND_REPORT,
                          params={"SHOWTYPE": "xlsx", "CATALOGID": "1000_lf"},
                          retries=2, headers=self._h("https://fund.szse.cn/"), timeout=25)
        df = pd.read_excel(io.BytesIO(r.content), engine="openpyxl", dtype={"基金代码": str})
        missing = {"基金代码", "基金类别", "当前规模(份)"} - set(df.columns)
        if missing:
            raise ValueError(f"etf_shares SZSE: xlsx missing columns {sorted(missing)}")
        # 基金类别 is ETF / LOF / 不动产基金 — LOFs and REITs are out of contract.
        etf = df[df["基金类别"].astype(str).str.strip() == "ETF"]
        shares = pd.to_numeric(
            etf["当前规模(份)"].astype(str).str.replace(",", "", regex=False).str.strip(),
            errors="coerce")
        out: dict[str, float] = {}
        for code, val in zip(etf["基金代码"].astype(str).str.strip(), shares):
            if code and pd.notna(val):
                out[f"sh_{code}"] = float(val)      # already raw 份
        if not out:
            raise ValueError("etf_shares SZSE: no ETF rows in the xlsx")
        log.info("china_flows etf_shares: SZSE %d ETFs (of %d fund rows)", len(out), len(df))
        return out

    def _etf_shares_em(self) -> pd.DataFrame:
        """LAST-RESORT fallback: the legacy 21-code EastMoney basket (CNH-R2 — a proxy
        transport is allowed only as a documented fallback behind the native one).

        Behaviour is unchanged from the pre-W2 collector, including the collection-date
        index (RPT_FUND_ETFLIST publishes no date field).
        """
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

    def _etf_shares(self, full_history: bool) -> pd.DataFrame:
        """One wide row of raw-份 shares outstanding for the whole official ETF universe.

        full_history is a no-op for this leg (same behaviour as nightly): neither exchange
        publishes a deep scale history, so depth accrues FORWARD one snapshot per session
        per the masterplan's CN-SYS accrual clock — a full-history run cannot buy history
        that was never published.

        Degrade ladder: one exchange down -> ship the other and log the gap; both down ->
        the EastMoney 21-code fallback; all three down -> ValueError, isolated per-series
        by fetch().  Total nightly calls <=6 (<=4 SSE walk-back + 1 SZSE + 1 fallback).
        """
        sse_row: dict[str, float] = {}
        as_of: pd.Timestamp | None = None
        try:
            sse_row, as_of = self._etf_shares_sse()
        except Exception as e:  # noqa: BLE001 — one exchange down is a gap, not a failure
            log.info("china_flows etf_shares: SSE leg unavailable (%s) — "
                     "Shanghai funds gap this session", e)
        szse_row: dict[str, float] = {}
        try:
            szse_row = self._etf_shares_szse()
        except Exception as e:  # noqa: BLE001
            log.info("china_flows etf_shares: SZSE leg unavailable (%s) — "
                     "Shenzhen funds gap this session", e)

        # Union; SSE wins a collision (codes are disjoint in practice — 5xxxxx vs 15xxxx).
        row: dict[str, float] = {**szse_row, **sse_row}
        if len(row) >= _MIN_UNIVERSE_COLS:
            if as_of is None:
                as_of = pd.Timestamp(self._cn_weekdays_back(1)[0])
                log.info("china_flows etf_shares: SZSE-only row stamped at %s "
                         "(no SSE STAT_DATE to borrow)", as_of.date())
            return pd.DataFrame(row, index=[as_of])

        if row:
            log.warning("china_flows etf_shares: only %d funds resolved (<%d) — a partial "
                        "universe would poison the per-fund z-scores; using the EastMoney "
                        "fallback basket instead", len(row), _MIN_UNIVERSE_COLS)
        try:
            return self._etf_shares_em()
        except Exception as e:  # noqa: BLE001 — surface one ValueError for the leg
            raise ValueError(
                "etf_shares: SSE, SZSE and the EastMoney fallback basket all failed "
                f"(fallback error: {e})") from e

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
