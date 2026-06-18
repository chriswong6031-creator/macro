"""Official Hang Seng A/H premium — the ~190-pair Eastmoney snapshot + a true
daily premium index, a cross-check on engine/hk_ah.py's computed ~12-pair basket.

Two akshare endpoints (Tencent/Eastmoney aggregators, keyless):

  ak.stock_zh_ah_spot_em()            live snapshot of ALL ~190 dual-listed A/H
                                      pairs (cols: 名称, H股代码, 最新价-HKD, A股代码,
                                      最新价-RMB, 比价 ratio, 溢价 premium%). The widest
                                      official read of the A/H premium — but it is a
                                      SNAPSHOT with no history, so we stamp it with
                                      today's date and accrue forward (the same pattern
                                      china_flows uses for its A-share gauges), letting a
                                      market-wide daily series build from each good run.

  ak.stock_zh_ah_daily(symbol=...)    per-pair daily history, BUT it returns the H-share
                                      OHLC only (日期/开盘/收盘/最高/最低/成交量) — NOT the
                                      premium. So we reconstruct a TRUE daily premium per
                                      pair the way engine/hk_ah does: convert each day's
                                      H close (HKD) into CNY via the stored USDCNY/USDHKD
                                      and compare to the A close (china_search/closes),
                                      premium% = (A_cny / H_in_cny - 1)*100, then
                                      equal-weight the most-liquid pairs into an index.

Stored under group `hk_ah_official`, two parquet:
  ah_spot      one accrue-forward row/run: hsahp (equal-weight MEAN premium across all
               resolved pairs), hsahp_median, n_pairs.
  ah_premium   the reconstructed daily premium INDEX (col hsahp), equal-weight over
               ~8-12 liquid bank/insurer/energy pairs back several years.

Gotchas, all live-verified 2026-06-17:
  - akshare raises ConnectionError / RemoteDisconnected / a bare requests.HTTPError
    (e.g. Eastmoney 502) rather than a clean status code, so EVERY akshare call is
    wrapped in an explicit retry loop with exponential backoff.
  - stock_zh_ah_daily iterates range(start_year, end_year) → end_year is EXCLUSIVE;
    pass next_year to include the current year.
  - the H symbol for stock_zh_ah_daily is the 5-digit code ("00939"), i.e. the .HK
    ticker zero-padded to 5 digits.
  - the per-pair daily histories overlap at year boundaries and the stored FX can
    carry duplicate dates → dedupe every series (keep last) before the inner join,
    or pandas raises "cannot reindex on an axis with duplicate labels".
  - 1:1 share-equivalence (no float/share-class adjustment) means the reconstructed
    LEVEL differs slightly from the spot 溢价; lean on the trend/percentile. ah_spot
    (the official 溢价) is the level anchor.

Display-only; degrades to absent. If the daily reconstruction resolves too few pairs
(daily endpoint slow/flaky, or china_search/closes + FX not yet collected) we ship
ah_spot alone. Only if BOTH series fail do we raise so the breaker can act.
"""
from __future__ import annotations

import logging
import time
from datetime import date

import akshare as ak
import pandas as pd

from collectors.base import Adapter
from lib import config, store

log = logging.getLogger(__name__)

# Fallback liquid roster (H.HK -> A-share store column) used to build the daily
# premium index when config.hk.ah_official.liquid_pairs is not set. Most-liquid
# mega-cap dual listings (banks / insurers / energy / BYD / Conch) — the deepest,
# cleanest A/H histories.
_DEFAULT_LIQUID = {
    "0939.HK": "601939.SS",   # China Construction Bank
    "1398.HK": "601398.SS",   # ICBC
    "3988.HK": "601988.SS",   # Bank of China
    "1288.HK": "601288.SS",   # Agricultural Bank of China
    "2318.HK": "601318.SS",   # Ping An Insurance
    "2628.HK": "601628.SS",   # China Life
    "0857.HK": "601857.SS",   # PetroChina
    "0386.HK": "600028.SS",   # Sinopec
    "1211.HK": "002594.SZ",   # BYD
    "0914.HK": "600585.SS",   # Anhui Conch Cement
}


class HkAhOfficialAdapter(Adapter):
    name = "hk_ah_official"
    group = "hk_ah_official"
    stale_after_days = 6   # trading-day series; tolerate a long weekend / HK+CN holiday

    def __init__(self) -> None:
        cfg = config.load().get("hk", {})
        self.cfg = cfg.get("ah_official", {}) or {}
        # liquid roster for the daily index: explicit override, else the curated default
        self.liquid_pairs: dict[str, str] = (
            self.cfg.get("liquid_pairs") or dict(_DEFAULT_LIQUID)
        )
        self.retries = int(self.cfg.get("retries", 3))
        self.backoff_base = float(self.cfg.get("backoff_base_s", 3.0))
        # daily-index history depth (years back from today)
        self.history_years = int(self.cfg.get("history_years", 5))
        self.live_years = int(self.cfg.get("live_years", 2))
        self.min_daily_pairs = int(self.cfg.get("min_daily_pairs", 5))

    # -- akshare retry wrapper (akshare raises ConnectionError, not http codes) -
    def _ak(self, fn, *args, **kwargs):
        last: Exception | None = None
        for attempt in range(self.retries):
            try:
                return fn(*args, **kwargs)
            except Exception as e:  # noqa: BLE001 — retried, then surfaced
                last = e
                if attempt == self.retries - 1:
                    raise
                time.sleep(self.backoff_base * (2 ** attempt))
        raise last  # type: ignore[misc]

    @staticmethod
    def _dedupe(s: pd.Series) -> pd.Series:
        return s[~s.index.duplicated(keep="last")].sort_index()

    @staticmethod
    def _hcode(hk_ticker: str) -> str:
        """'0939.HK' -> '00939' (5-digit H code stock_zh_ah_daily expects)."""
        return hk_ticker.split(".")[0].lstrip("^").zfill(5)

    # -- ah_spot: market-wide snapshot, accrued forward -----------------------
    def _ah_spot(self) -> pd.DataFrame:
        raw = self._ak(ak.stock_zh_ah_spot_em)
        if raw is None or raw.empty or "溢价" not in raw.columns:
            raise ValueError("ah_spot: empty / no 溢价 column")
        prem = pd.to_numeric(raw["溢价"], errors="coerce").dropna()
        if prem.empty:
            raise ValueError("ah_spot: no usable premium values")
        row = {
            "hsahp": round(float(prem.mean()), 3),       # equal-weight market-wide mean
            "hsahp_median": round(float(prem.median()), 3),
            "n_pairs": int(prem.shape[0]),
        }
        return pd.DataFrame([row], index=[pd.Timestamp(date.today())])

    # -- ah_premium: reconstructed true daily premium index -------------------
    def _ah_premium(self, full_history: bool) -> pd.DataFrame:
        # shared common-currency inputs (same trusted inputs engine/hk_ah uses)
        a_closes = store.read("china_search", "closes")
        cny = store.read("china", "CNY=X")    # CNY per USD
        hkd = store.read("hk", "HKD=X")       # HKD per USD
        if a_closes is None or a_closes.empty:
            raise ValueError("ah_premium: china_search/closes unavailable")
        if (cny is None or "close" not in cny.columns
                or hkd is None or "close" not in hkd.columns):
            raise ValueError("ah_premium: USDCNY/USDHKD FX unavailable")
        usdcny = self._dedupe(cny["close"].dropna())
        usdhkd = self._dedupe(hkd["close"].dropna())
        cny_per_hkd = self._dedupe((usdcny / usdhkd).dropna())   # ~0.86-0.91
        if cny_per_hkd.empty:
            raise ValueError("ah_premium: empty CNY/HKD cross")

        this_year = date.today().year
        start = this_year - (self.history_years if full_history else self.live_years)
        end = this_year + 1   # end_year is EXCLUSIVE in stock_zh_ah_daily

        per_pair: dict[str, pd.Series] = {}
        errors: list[str] = []
        for hk, acol in self.liquid_pairs.items():
            try:
                if acol not in a_closes.columns:
                    raise ValueError(f"A column {acol} not in china_search/closes")
                raw = self._ak(ak.stock_zh_ah_daily, symbol=self._hcode(hk),
                               start_year=str(start), end_year=str(end))
                if raw is None or raw.empty or "收盘" not in raw.columns or "日期" not in raw.columns:
                    raise ValueError("empty H daily / missing 收盘|日期")
                h = self._dedupe(pd.Series(
                    pd.to_numeric(raw["收盘"], errors="coerce").to_numpy(),
                    index=pd.to_datetime(raw["日期"]),
                ).dropna())
                a = self._dedupe(a_closes[acol].dropna())
                if h.empty or a.empty:
                    raise ValueError("no H or A closes")
                df = pd.concat({"h": h, "a": a, "fx": cny_per_hkd},
                               axis=1, join="inner").dropna()
                if df.empty:
                    raise ValueError("no overlapping A/H/FX dates")
                prem = ((df["a"] / (df["h"] * df["fx"]) - 1.0) * 100.0).dropna()
                if prem.empty:
                    raise ValueError("no usable premium values")
                per_pair[hk] = prem
            except Exception as e:  # noqa: BLE001 — per-pair isolation
                errors.append(f"{hk}: {e}")
                log.warning("hk_ah_official daily pair %s failed: %s", hk, e)

        if len(per_pair) < self.min_daily_pairs:
            raise ValueError(
                f"ah_premium: only {len(per_pair)}/{len(self.liquid_pairs)} pairs "
                f"(need {self.min_daily_pairs}) — " + " | ".join(errors))
        if errors:
            log.info("hk_ah_official: %d/%d daily pairs ok (skipped: %s)",
                     len(per_pair), len(per_pair) + len(errors), "; ".join(errors))

        basket = pd.concat(per_pair, axis=1).sort_index().mean(axis=1).dropna()
        if basket.empty:
            raise ValueError("ah_premium: empty equal-weight basket")
        return pd.DataFrame({"hsahp": basket.round(3)})

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        frames: dict[str, pd.DataFrame] = {}
        errors: list[str] = []
        for key, fn in (("ah_spot", lambda: self._ah_spot()),
                        ("ah_premium", lambda: self._ah_premium(full_history))):
            try:
                frames[key] = fn()
            except Exception as e:  # noqa: BLE001 — per-series isolation
                errors.append(f"{key}: {e}")
                log.warning("hk_ah_official %s failed: %s", key, e)
        if not frames:
            raise RuntimeError("hk_ah_official: all series failed — " + " | ".join(errors))
        if errors:
            log.info("hk_ah_official: %d/%d series ok (skipped: %s)",
                     len(frames), len(frames) + len(errors), "; ".join(errors))
        return frames
