"""Whole-board A-share 涨跌家数 — the advance/decline count the market actually prints.

WHY THIS EXISTS. The A-share heatmap's breadth card counted its own TILES
(``site/heatmap.js`` ``computeSummary``), and the tile universe is
``data/china_search/members.parquet`` — Sina top-800 by market cap ∪ CSI 300 ∪
CSI 1000 ∪ config extras ≈ 1,510 names. So the card printed "▲154 / 1346▼" on a
board of ~5,200 names. The RATIO was sound (that panel covers 82% of A-share
market cap and ~73% of daily turnover), but 涨跌家数 is a whole-board count by
convention: a user cross-checking 东方财富 sees a denominator 3.4x larger and
reads ours as broken. This adapter supplies the real count so the card can stop
quoting a sample as if it were the board.

SCOPE — 沪深 only (Shanghai + Shenzhen), matching the convention most Chinese
breadth prints use. 北交所 (BSE, ~330 names, codes 4xx/8xx/9xx) is excluded: it
is thinly traded and would drag the reading around on very low volume. The
excluded board is named in the payload receipt, never silently dropped.

SOURCES (premium primary, keyless fallback — the house pattern from
``tushare_valuation`` ↔ ``china_a_val``):

  1. Tushare ``daily`` (120积分, inside the ¥500/5000积分 tier) — ONE
     ``trade_date=`` call returns every name that traded, with an exact session
     date. Gated on ``TUSHARE_TOKEN``; this is what nightly uses.
  2. Sina ``Market_Center.getHQNodeData`` node=hs_a, paged — keyless, ~69 pages.
     Slower and rate-limit-prone (hence the adapter's retry/backoff), but it
     works without a token and from a non-CN IP. Eastmoney's push2 whole-market
     spot (``ak.stock_zh_a_spot_em``) is NOT usable here — it resets the
     connection from a non-CN IP, the same failure that made this repo buy
     Tushare in the first place.

OUTPUT (``data/china_board_breadth/breadth.parquet``) — one row per SESSION,
indexed by the trade date (not the run date), so a same-session re-run overwrites
rather than duplicating, and the index itself is the freshness key the heatmap
builder gates on:

  n        — names that traded (the denominator; suspended names are excluded)
  adv      — 涨 count (% change > 0)
  dec      — 跌 count (% change < 0)
  flat     — 平 count (% change == 0)
  pct_up   — 100 * adv / n
  med_pct  — median % change across the board
  source   — 'tushare' | 'sina' (the receipt; which plane produced the row)

COUNT CONVENTION. 涨/跌/平 split on strict zero, which is what 东方财富 and
同花顺 print — deliberately NOT the ±0.05% dead-band the tile-derived fallback in
heatmap.js uses. The two differ by a handful of names out of ~5,200; matching the
convention matters more for a number whose whole purpose is cross-checkability.

DISPLAY-TIER. A count of what happened today — no forward claim, nothing scored.
"""
from __future__ import annotations

import logging
import time

import pandas as pd

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)

_SINA_URL = ("https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
             "Market_Center.getHQNodeData")
_SINA_DATE_URL = "https://hq.sinajs.cn/list=sh000001"   # 上证指数 line carries the session date
_SINA_REFERER = "https://finance.sina.com.cn/"
_SINA_PAGE_SIZE = 80
_SINA_MAX_PAGES = 90          # ~5,200 沪深 names / 80 per page = 65, plus headroom
_MIN_NAMES = 3000             # floor for a credible whole-board read (board is ~5,200)


def _is_hushen(code: str) -> bool:
    """True for a Shanghai/Shenzhen A-share code; False for 北交所 and anything odd.

    600/601/603/605 = 沪主板, 688 = 科创板, 000/001/002/003 = 深主板, 300/301 = 创业板.
    4xx / 8xx / 9xx = 北交所 or B-share — out of scope (see module docstring).
    """
    c = code.strip()
    if len(c) != 6 or not c.isdigit():
        return False
    return c[:2] in ("60", "68") or c[0] in ("0", "3")


def _counts(pct: pd.Series, source: str, trade_date: pd.Timestamp) -> pd.DataFrame:
    """adv/dec/flat frame for one session. 涨/跌/平 split on strict zero (see docstring)."""
    n = int(len(pct))
    if n < _MIN_NAMES:
        raise ValueError(f"china_board_breadth: {source} returned {n} names "
                         f"(< {_MIN_NAMES}) — treating as a half-failed pull, not a real board")
    adv = int((pct > 0).sum())
    dec = int((pct < 0).sum())
    flat = n - adv - dec
    df = pd.DataFrame(
        {"n": [n], "adv": [adv], "dec": [dec], "flat": [flat],
         "pct_up": [round(100.0 * adv / n, 2)],
         "med_pct": [round(float(pct.median()), 4)],
         "source": [source]},
        index=pd.DatetimeIndex([trade_date], name="date"),
    )
    log.info("china_board_breadth [%s] %s: %d traded — %d up / %d down / %d flat (%.1f%% up)",
             source, trade_date.date(), n, adv, dec, flat, df["pct_up"].iloc[0])
    return df


class ChinaBoardBreadthAdapter(Adapter):
    """Whole-board 沪深 A-share adv/dec, one row per trading session."""

    name = "china_board_breadth"
    group = "china_board_breadth"
    stale_after_days = 6   # daily plane; tolerant of a Golden Week / Spring Festival close
    # Both planes are external and flaky (Tushare needs a token; Sina rate-limits a
    # 69-page walk). A break must report 'blocked' and leave the heatmap on its
    # tile-derived fallback — never trip the breaker for the whole asia lane.
    expected_failure = "whole-board A-share snapshot unavailable (Tushare gated / Sina throttled)"

    def __init__(self) -> None:
        self.ycfg = config.load()["china"]["yahoo"]   # shared retries / backoff_base_s

    # -- plane 1: Tushare daily (whole board in one call) ----------------------
    def _from_tushare(self) -> pd.DataFrame | None:
        from collectors import tushare_client as tc
        if not tc.enabled():
            return None
        df, trade_date = tc.snapshot_by_date("daily", fields="ts_code,trade_date,pct_chg,close")
        if df is None or df.empty or "pct_chg" not in df.columns:
            log.warning("china_board_breadth: tushare daily returned nothing usable")
            return None
        codes = df["ts_code"].astype(str).str.split(".").str[0]
        keep = codes.map(_is_hushen) & ~codes.duplicated(keep="last")
        pct = pd.to_numeric(df.loc[keep, "pct_chg"], errors="coerce").dropna()
        return _counts(pct, "tushare", pd.Timestamp(trade_date))

    # -- plane 2: Sina hs_a page walk (keyless) --------------------------------
    def _sina_session_date(self) -> pd.Timestamp:
        """Session date from the 上证指数 quote line (field -3 is the date)."""
        r = self.http_get(_SINA_DATE_URL, retries=self.ycfg["retries"],
                          backoff_base=self.ycfg["backoff_base_s"], timeout=20,
                          headers={"Referer": _SINA_REFERER})
        body = r.text.split('"')[1] if '"' in r.text else ""
        for part in reversed(body.split(",")):
            part = part.strip()
            if len(part) == 10 and part[4] == "-" and part[7] == "-":
                return pd.Timestamp(part)
        raise ValueError(f"china_board_breadth: no session date in Sina quote line: {r.text[:120]!r}")

    def _from_sina(self) -> pd.DataFrame:
        trade_date = self._sina_session_date()
        moves: dict[str, float] = {}
        for page in range(1, _SINA_MAX_PAGES + 1):
            r = self.http_get(_SINA_URL, retries=self.ycfg["retries"],
                              backoff_base=self.ycfg["backoff_base_s"], timeout=30,
                              params={"page": page, "num": _SINA_PAGE_SIZE, "sort": "mktcap",
                                      "asc": 0, "node": "hs_a", "symbol": "", "_s_r_a": "page"},
                              headers={"Referer": _SINA_REFERER})
            try:
                data = r.json()
            except Exception:  # noqa: BLE001 — Sina returns null/garbage past the last page
                data = None
            if not data:
                break
            for d in data:
                code = str(d.get("code") or "")
                if not _is_hushen(code):
                    continue
                # A suspended name quotes trade=0 and never moves — excluding it keeps
                # 平 honest (a halt is not a flat print).
                try:
                    last = float(d.get("trade") or 0)
                    pct = float(d.get("changepercent"))
                except (TypeError, ValueError):
                    continue
                if last > 0:
                    moves[code] = pct
            time.sleep(0.45)   # a tighter walk gets the connection reset
        return _counts(pd.Series(moves, dtype="float64"), "sina", trade_date)

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        # Snapshot-only planes: full_history is a no-op (neither source backfills a
        # historical adv/dec count). Each run lands exactly one row, stamped with the
        # session it describes; store.upsert overwrites a same-session re-run.
        try:
            df = self._from_tushare()
            if df is not None:
                return {"breadth": df}
            log.info("china_board_breadth: no Tushare token — falling back to the Sina walk")
        except Exception as e:  # noqa: BLE001 — premium plane down must fall through, not fail
            log.warning("china_board_breadth: tushare plane failed (%s); trying Sina", e)
        return {"breadth": self._from_sina()}
