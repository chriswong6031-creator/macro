"""China convertible-bond plane — the A-share risk-appetite read that equity breadth
misses. Masterplan W2, research/china_native_data/CHINA_HK_NATIVE_DATA_MASTERPLAN_BY_FABLE.md
§W2. DISPLAY-TIER CONTEXT ONLY: both series are collected and accrued, neither is
scored, ranked, or gated on.

  breadth  full-universe convertible-bond breadth from EastMoney RPT_BOND_CB_LIST
           (~1,038 rows today, uncapped and keyless): how many CBs are listed, the
           median bond price and conversion premium, the share trading below par, the
           share at redemption-risk levels (≥130), and the 双低 (double-low: cheap AND
           low-premium) share that CB desks watch as the crowding tell. LIVE SNAPSHOT
           (the report carries no data date), so it is dated by the COLLECTION date in
           Asia/Shanghai and SKIPPED ENTIRELY on Sat/Sun rather than stamping a weekend
           row onto a stale Friday quote.
  index    jisilu equal-weight CB index history (集思录可转债指数) from the KEYLESS
           /webapi/cb/index_history/ endpoint: index level, constituent count, mean and
           median price/premium/YTM, the 双低 mean, a temperature reading, and turnover.
           The endpoint serves a ROLLING ~1-year window, so the store accrues forward:
           every run upserts the current window and older rows already on disk stay.
           The login-capped list endpoint (/data/cbnew/cb_list_new) is NEVER used — it
           gates guests to 30 of ~316 rows, and stepping past that is an access control,
           not a parse problem (CNH-R5/R6).

Each series degrades independently (same isolation shape as collectors/china_flows.py):
a blocked source just leaves its parquet to grow from the next good day — never a
zero-fill, never a silent gap.

Pacing: ≤1 request/second per host; the nightly path is ~4 HTTP calls (3 EastMoney
pages + 1 jisilu).
"""
from __future__ import annotations

import logging
import math
import time
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd

from collectors.base import Adapter

log = logging.getLogger(__name__)

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# -- endpoints (VERIFIED live 2026-07-25; see SOURCE_CATALOG_MARKET.md) -------------
_DC = "https://datacenter-web.eastmoney.com/api/data/v1/get"
_JISILU_INDEX = "https://www.jisilu.cn/webapi/cb/index_history/"

_HOST_PACE_S = 1.0          # ≤1 req/s per host — house law for every China source
_CB_REPORT = "RPT_BOND_CB_LIST"
_CB_PAGE_SIZE = 500        # ~1,038 rows => 3 pages today (nightly = 3 + 1 jisilu call)
_CB_MAX_PAGES = 6          # runaway guard (3,000 bonds ≈ 2.9x today's universe); a pull
                           # that hits the cap logs the truncation loudly rather than
                           # quietly aggregating the newest slice only
# Quote joins EastMoney serves alongside the static CB fields (underlying price,
# conversion price/value, current bond price, conversion premium %).
_CB_QUOTE_COLUMNS = ("f2~01~CONVERT_STOCK_CODE~CONVERT_STOCK_PRICE,"
                     "f235~10~SECURITY_CODE~TRANSFER_PRICE,"
                     "f236~10~SECURITY_CODE~TRANSFER_VALUE,"
                     "f2~10~SECURITY_CODE~CURRENT_BOND_PRICE,"
                     "f237~10~SECURITY_CODE~TRANSFER_PREMIUM_RATIO")

# 双低 / double-low thresholds — the standard CB crowding read (cheap bond AND thin
# premium). Named constants, not inline magic numbers, because the cut is a convention.
DOUBLE_LOW_PRICE = 115.0
DOUBLE_LOW_PREMIUM = 15.0
PRICE_BELOW_PAR = 100.0      # sub-par: bond-floor territory
PRICE_REDEMPTION = 130.0     # ≥130 = forced-redemption / equity-like territory
# Below this many priced rows the quote join has broken (thin aggregate would be a lie).
MIN_PRICED = 50

# jisilu index_history keys kept — every one is an array ALIGNED to price_dt.
_JSL_KEEP = ("price", "count", "avg_price", "mid_price", "avg_premium_rt",
             "mid_premium_rt", "avg_ytm_rt", "avg_dblow", "temperature",
             "turnover_rt", "idx_price")


def _pct(n: int, total: int) -> float:
    """n as a PERCENT of total (0-100), NaN when total is 0. Pure."""
    return round(100.0 * n / total, 2) if total else float("nan")


def aggregate_breadth(rows: list[dict]) -> dict:
    """RPT_BOND_CB_LIST rows -> one snapshot row of universe breadth aggregates.

    Universe = LISTING_DATE non-null AND DELIST_DATE null (unlisted new issues and
    delisted bonds are excluded). CURRENT_BOND_PRICE is sometimes the STRING "-" and
    TRANSFER_PREMIUM_RATIO can be negative, so both are coerced with errors="coerce"
    and a non-numeric price simply leaves that bond unpriced.

    Raises when fewer than MIN_PRICED bonds carry a numeric price — that means the
    quote join broke upstream, and a loud failure beats a fabricated thin aggregate.

    pct_* columns are PERCENTAGES of n_priced (0-100), not fractions. issue_scale_sum
    is in 亿元 (the report's own unit). There is no remaining-size field in this
    report, so none is reported. Pure — no I/O, no clock.
    """
    listed = [r for r in (rows or [])
              if isinstance(r, dict) and r.get("LISTING_DATE") and not r.get("DELIST_DATE")]
    n_listed = len(listed)
    price = pd.to_numeric(
        pd.Series([r.get("CURRENT_BOND_PRICE") for r in listed], dtype="object"),
        errors="coerce")
    premium = pd.to_numeric(
        pd.Series([r.get("TRANSFER_PREMIUM_RATIO") for r in listed], dtype="object"),
        errors="coerce")
    scale = pd.to_numeric(
        pd.Series([r.get("ACTUAL_ISSUE_SCALE") for r in listed], dtype="object"),
        errors="coerce")

    priced = price.notna()
    n_priced = int(priced.sum())
    if n_priced < MIN_PRICED:
        raise ValueError(
            f"cb breadth: only {n_priced} of {n_listed} listed CBs carry a numeric "
            f"price (floor {MIN_PRICED}) — the EastMoney quote join is broken")
    p = price[priced]
    prem = premium[priced]
    # A priced bond with a NaN premium fails the double-low test rather than passing it
    # on a missing value (NaN < threshold is False) — no imputation.
    n_double_low = int(((p < DOUBLE_LOW_PRICE) & (prem < DOUBLE_LOW_PREMIUM)).sum())
    return {
        "n_listed": float(n_listed),
        "n_priced": float(n_priced),
        "price_med": float(p.median()),
        "price_mean": float(p.mean()),
        "premium_med": float(prem.median()),
        "premium_mean": float(prem.mean()),
        "pct_price_lt_100": _pct(int((p < PRICE_BELOW_PAR).sum()), n_priced),
        "pct_price_ge_130": _pct(int((p >= PRICE_REDEMPTION).sum()), n_priced),
        "pct_double_low": _pct(n_double_low, n_priced),
        # NaN (not 0.0) when the report served no scales at all — an absent field is a
        # gap, and a fabricated zero would read as "nothing was ever issued".
        "issue_scale_sum": float(scale.sum()) if bool(scale.notna().any()) else float("nan"),
    }


def parse_index_history(payload: dict) -> pd.DataFrame:
    """jisilu index_history payload -> frame indexed by price_dt.

    data{} is a dict of ALIGNED arrays. Any kept key whose length differs from
    price_dt raises: mis-zipping arrays would silently shift a whole series against
    its own dates. A key the endpoint stops serving is logged and skipped (the frame
    narrows honestly). Pure.
    """
    data = (payload or {}).get("data") or {}
    dates = data.get("price_dt") or []
    n = len(dates)
    if not n:
        raise ValueError("cb index: payload carried no price_dt array")
    cols: dict[str, pd.Series] = {}
    for key in _JSL_KEEP:
        arr = data.get(key)
        if arr is None:
            log.warning("china_cb index: key %r absent from the payload — column "
                        "omitted for this run", key)
            continue
        if len(arr) != n:
            raise ValueError(
                f"cb index: '{key}' has {len(arr)} entries but price_dt has {n} — "
                f"misaligned arrays, refusing to zip them")
        # float64 for every column, even integral ones like `count`: a column that
        # parses as int64 today and float64 the first day it carries a NaN would flip
        # the parquet schema under the store.
        cols[key] = pd.to_numeric(pd.Series(list(arr), dtype="object"),
                                  errors="coerce").astype("float64")
    if not cols:
        raise ValueError("cb index: none of the expected value arrays were present")
    idx = pd.to_datetime(pd.Series([str(d) for d in dates]), errors="coerce")
    df = pd.DataFrame(cols)
    df.index = idx
    df = df[df.index.notna()]
    if df.empty:
        raise ValueError("cb index: no rows with a parseable price_dt")
    return df[~df.index.duplicated(keep="last")].sort_index()


class ChinaCbAdapter(Adapter):
    name = "china_cb"
    group = "china_cb"   # 'china_' prefix auto-routes to the asia lane
    stale_after_days = 6

    def _h(self, referer: str) -> dict:
        return {"User-Agent": _UA, "Referer": referer}

    def _today_cn(self) -> date:
        """Collection date on the market's own calendar (Asia/Shanghai).

        Overridable in tests so the weekend guard is exercisable without freezing
        the process clock.
        """
        return datetime.now(ZoneInfo("Asia/Shanghai")).date()

    # -- full-universe CB breadth ----------------------------------------------
    def _cb_rows(self) -> list[dict]:
        """Page through RPT_BOND_CB_LIST. ≤1 req/s, ≤_CB_MAX_PAGES calls."""
        rows: list[dict] = []
        page, total_pages = 1, 1
        while page <= min(total_pages, _CB_MAX_PAGES):
            params = {"reportName": _CB_REPORT, "columns": "ALL",
                      "quoteColumns": _CB_QUOTE_COLUMNS,
                      "pageSize": _CB_PAGE_SIZE, "pageNumber": page,
                      "sortColumns": "PUBLIC_START_DATE", "sortTypes": -1,
                      "source": "WEB", "client": "WEB"}
            r = self.http_get(_DC, params=params, retries=2,
                              headers=self._h("https://data.eastmoney.com/"), timeout=25)
            result = (r.json() or {}).get("result") or {}
            data = result.get("data") or []
            rows.extend(d for d in data if isinstance(d, dict))
            # NB: `x or 0` on a pandas NaN keeps the NaN (NaN is truthy) — check notna
            # explicitly rather than leaning on truthiness.
            declared_raw = pd.to_numeric(result.get("pages"), errors="coerce")
            declared = int(declared_raw) if pd.notna(declared_raw) else 0
            if declared <= 0:
                count = pd.to_numeric(result.get("count"), errors="coerce")
                declared = (int(math.ceil(float(count) / _CB_PAGE_SIZE))
                            if pd.notna(count) and float(count) > 0 else 1)
            total_pages = declared
            if page >= total_pages:
                break
            page += 1
            time.sleep(_HOST_PACE_S)
        if total_pages > _CB_MAX_PAGES:
            log.warning("china_cb breadth: universe now spans %d pages but the nightly "
                        "cap is %d — aggregates cover the first %d rows only",
                        total_pages, _CB_MAX_PAGES, len(rows))
        return rows

    def _breadth(self, full_history: bool) -> pd.DataFrame | None:
        today = self._today_cn()
        if today.weekday() >= 5:
            # Live snapshot with no upstream date: a weekend row would stamp Friday's
            # stale quote onto Saturday. Skip the series instead (not an error).
            log.info("china_cb breadth: %s is a weekend in Asia/Shanghai — snapshot "
                     "leg skipped (no frame, no stale row)", today)
            return None
        agg = aggregate_breadth(self._cb_rows())
        return pd.DataFrame(agg, index=[pd.Timestamp(today)])

    # -- jisilu equal-weight CB index ------------------------------------------
    def _index(self, full_history: bool) -> pd.DataFrame:
        # Keyless, UA-only. Rolling ~1y window: full_history == nightly, and upsert
        # accrues the history forward beyond what the endpoint still serves.
        r = self.http_get(_JISILU_INDEX, retries=2,
                          headers=self._h("https://www.jisilu.cn/data/cbnew/"),
                          timeout=25)
        return parse_index_history(r.json() or {})

    # -- fetch -----------------------------------------------------------------
    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        frames: dict[str, pd.DataFrame] = {}
        errors: list[str] = []
        skipped: list[str] = []
        for key, fn in (("breadth", self._breadth), ("index", self._index)):
            try:
                df = fn(full_history)
            except Exception as e:  # noqa: BLE001 — per-series isolation
                errors.append(f"{key}: {e}")
                log.warning("china_cb %s failed: %s", key, e)
                continue
            if df is None or df.empty:
                skipped.append(key)   # deliberate skip (weekend snapshot), not a failure
                continue
            frames[key] = df
        if not frames:
            raise RuntimeError("china_cb: no series produced — "
                               + " | ".join(errors + [f"{k}: skipped" for k in skipped]))
        if errors or skipped:
            log.info("china_cb: %d/%d series ok (failed: %s; skipped: %s)",
                     len(frames), len(frames) + len(errors) + len(skipped),
                     "; ".join(errors) or "none", "; ".join(skipped) or "none")
        return frames
