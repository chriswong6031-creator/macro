"""Restricted-share unlock queue collector for A-share names (keyless, via akshare/Eastmoney).

A-share restricted shares (限售股) are locked at IPO and unlock in tranches. Large
unlock events — especially those that are a significant fraction of pre-unlock float
(占解禁前流通市值比例) — can create supply pressure and are a key special-situations signal.

Two tables are fetched:
  1. aggregate: ak.stock_restricted_release_summary_em(symbol='全部股票', ...)
     → daily forward calendar aggregate (unlock count / quantity / mktcap)
  2. detail:    ak.stock_restricted_release_detail_em(start_date=..., end_date=...)
     → per-name events with codes, unlock type, float-impact ratio, pre-event drift

Stored under:
  data/china_unlocks/summary.parquet  — aggregate forward calendar
  data/china_unlocks/detail.parquet   — per-name event rows

CONTEXT-ONLY. A large unlock is a risk context / supply-pressure flag, not a directional
signal (short-selling restrictions make the setup asymmetric and the edge unvalidated).
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta

import pandas as pd

from lib import config
from collectors.china_analyst import to_ticker, _num

log = logging.getLogger("china_unlocks")

_SUMMARY_OUT = config.data_dir() / "china_unlocks" / "summary.parquet"
_DETAIL_OUT   = config.data_dir() / "china_unlocks" / "detail.parquet"


def _col(cols: list[str], *needles: str) -> str | None:
    """First column whose name contains ALL needles (akshare names drift across versions)."""
    for c in cols:
        s = str(c)
        if all(n in s for n in needles):
            return c
    return None


def _today_str() -> str:
    return pd.Timestamp.utcnow().strftime("%Y-%m-%d")


def _date_plus(base: str, days: int) -> str:
    """Add `days` to a YYYY-MM-DD string, return YYYYMMDD."""
    return (datetime.strptime(base, "%Y-%m-%d") + timedelta(days=days)).strftime("%Y%m%d")


def _to_yyyymmdd(s: str) -> str:
    """Convert YYYY-MM-DD to YYYYMMDD."""
    return s.replace("-", "")


def refresh() -> int:
    """Fetch summary + detail unlock tables. Returns total rows written (0 on failure)."""
    today = _today_str()
    # Idempotency: if both parquets are fresh, skip
    if _SUMMARY_OUT.exists() and _DETAIL_OUT.exists():
        try:
            fresh_sum = str(pd.read_parquet(_SUMMARY_OUT, columns=["asof"])["asof"].max()) >= today
            fresh_det = str(pd.read_parquet(_DETAIL_OUT,   columns=["asof"])["asof"].max()) >= today
            if fresh_sum and fresh_det:
                log.info("china unlocks: cache already fresh (%s)", today)
                return 0
        except Exception:  # noqa: BLE001
            pass

    import akshare as ak

    total = 0

    # ── 1. summary aggregate ──────────────────────────────────────────────────
    today_yyyymmdd  = _to_yyyymmdd(today)
    end60_yyyymmdd  = _date_plus(today, 60)
    try:
        df_sum = ak.stock_restricted_release_summary_em(
            symbol="全部股票",
            start_date=today_yyyymmdd,
            end_date=end60_yyyymmdd,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("china unlocks: summary fetch failed (%s)", e)
        df_sum = None
    time.sleep(1.0)

    if df_sum is not None and not df_sum.empty:
        cols = list(df_sum.columns)
        # normalise date column (can be datetime.date objects)
        date_col = _col(cols, "日期") or _col(cols, "解禁日期")
        if date_col:
            df_sum[date_col] = pd.to_datetime(df_sum[date_col]).dt.date
        df_sum["asof"] = today
        _SUMMARY_OUT.parent.mkdir(parents=True, exist_ok=True)
        df_sum.to_parquet(_SUMMARY_OUT, index=False)
        total += len(df_sum)
        log.info("china unlocks: summary %d rows → %s", len(df_sum), _SUMMARY_OUT)
    else:
        log.info("china unlocks: summary empty or failed")

    # ── 2. per-name detail ────────────────────────────────────────────────────
    start30_yyyymmdd = _date_plus(today, -30)
    end90_yyyymmdd   = _date_plus(today, +90)
    try:
        df_det = ak.stock_restricted_release_detail_em(
            start_date=start30_yyyymmdd,
            end_date=end90_yyyymmdd,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("china unlocks: detail fetch failed (%s)", e)
        df_det = None
    time.sleep(1.2)

    if df_det is not None and not df_det.empty:
        cols = list(df_det.columns)
        # normalise date columns (come back as datetime.date objects)
        for dc in cols:
            if "时间" in dc or "日期" in dc:
                try:
                    df_det[dc] = pd.to_datetime(df_det[dc]).dt.date
                except Exception:  # noqa: BLE001
                    pass
        # extract ticker
        code_col = _col(cols, "代码") or _col(cols, "股票代码")
        if code_col:
            df_det["ticker"] = df_det[code_col].apply(to_ticker)
        df_det["asof"] = today
        _DETAIL_OUT.parent.mkdir(parents=True, exist_ok=True)
        df_det.to_parquet(_DETAIL_OUT, index=False)
        total += len(df_det)
        log.info("china unlocks: detail %d rows → %s", len(df_det), _DETAIL_OUT)
    else:
        log.info("china unlocks: detail empty or failed")

    return total


def main() -> int:
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    argparse.ArgumentParser(description="Fetch A-share unlock queue").parse_args()
    n = refresh()
    return 0 if n >= 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
