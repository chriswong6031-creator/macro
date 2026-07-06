"""Earnings pre-announcement collector for A-share names (keyless, via akshare/Eastmoney).

A-share companies are required to pre-announce earnings expectations before the formal
disclosure season:
  * 业绩预告 (yjyg): forecast type (预增/预减/首亏/扭亏/略增/续亏/续盈/略减) + magnitude range
  * 业绩快报 (yjkb): preliminary actual earnings (released before the full report)

Both tables are fetched for the current (or most recent available) quarter-end and
the prior quarter-end (so the desk isn't empty between seasons).

Stored under:
  data/china_preannounce/forecast.parquet  — yjyg rows
  data/china_preannounce/preliminary.parquet — yjkb rows

CONTEXT-ONLY. Direction labels are the EXCHANGE-REPORTED 预告类型, never originated here.
"""
from __future__ import annotations

import logging
import time
from datetime import date

import pandas as pd

from lib import config
from collectors.china_analyst import to_ticker, _num

log = logging.getLogger("china_preannounce")

_FORECAST_OUT     = config.data_dir() / "china_preannounce" / "forecast.parquet"
_PRELIMINARY_OUT  = config.data_dir() / "china_preannounce" / "preliminary.parquet"

# Quarter-end calendar mapping
_QUARTER_ENDS = {1: "0331", 2: "0630", 3: "0930", 4: "1231"}


def _col(cols: list[str], *needles: str) -> str | None:
    for c in cols:
        s = str(c)
        if all(n in s for n in needles):
            return c
    return None


def _today_str() -> str:
    return pd.Timestamp.utcnow().strftime("%Y-%m-%d")


def _quarter_end_dates(today: date, n: int = 2) -> list[str]:
    """Return the n most recent quarter-end YYYYMMDD strings <= today."""
    out: list[str] = []
    year = today.year
    while len(out) < n:
        for q in reversed(range(1, 5)):
            mmdd = _QUARTER_ENDS[q]
            d = date(year, int(mmdd[:2]), int(mmdd[2:]))
            if d <= today:
                out.append(d.strftime("%Y%m%d"))
                if len(out) >= n:
                    break
        year -= 1
    return out


def _fetch_forecast(quarter_yyyymmdd: str) -> pd.DataFrame | None:
    """Fetch yjyg (预告) for a quarter-end. Returns None on any failure."""
    import akshare as ak
    try:
        df = ak.stock_yjyg_em(date=quarter_yyyymmdd)
    except Exception as e:  # noqa: BLE001
        log.warning("china preannounce: yjyg(%s) failed (%s)", quarter_yyyymmdd, e)
        return None
    if df is None or df.empty:
        return None
    return df


def _fetch_preliminary(quarter_yyyymmdd: str) -> pd.DataFrame | None:
    """Fetch yjkb (快报) for a quarter-end. Returns None on any failure or no data."""
    import akshare as ak
    try:
        df = ak.stock_yjkb_em(date=quarter_yyyymmdd)
    except Exception as e:  # noqa: BLE001
        log.warning("china preannounce: yjkb(%s) failed (%s)", quarter_yyyymmdd, e)
        return None
    if df is None or df.empty:
        return None
    return df


def refresh() -> int:
    """Fetch forecast and preliminary earnings tables. Returns total rows written (0 on failure)."""
    today_str = _today_str()
    # Idempotency: skip if both are fresh
    if _FORECAST_OUT.exists() and _PRELIMINARY_OUT.exists():
        try:
            fsh = str(pd.read_parquet(_FORECAST_OUT,    columns=["asof"])["asof"].max()) >= today_str
            psh = str(pd.read_parquet(_PRELIMINARY_OUT, columns=["asof"])["asof"].max()) >= today_str
            if fsh and psh:
                log.info("china preannounce: cache already fresh (%s)", today_str)
                return 0
        except Exception:  # noqa: BLE001
            pass

    today = date.today()
    quarter_dates = _quarter_end_dates(today, n=2)
    total = 0

    # ── 1. Forecast (yjyg) ────────────────────────────────────────────────────
    forecast_frames: list[pd.DataFrame] = []
    for qd in quarter_dates:
        df = _fetch_forecast(qd)
        time.sleep(1.0)
        if df is not None:
            cols = list(df.columns)
            code_col = _col(cols, "代码") or _col(cols, "股票代码")
            if code_col:
                df["ticker"] = df[code_col].apply(to_ticker)
            df["quarter"] = qd
            df["asof"] = today_str
            forecast_frames.append(df)

    if forecast_frames:
        combined = pd.concat(forecast_frames, ignore_index=True)
        _FORECAST_OUT.parent.mkdir(parents=True, exist_ok=True)
        combined.to_parquet(_FORECAST_OUT, index=False)
        total += len(combined)
        log.info("china preannounce: forecast %d rows → %s", len(combined), _FORECAST_OUT)
    else:
        log.info("china preannounce: forecast empty for quarters %s", quarter_dates)

    # ── 2. Preliminary actuals (yjkb) ─────────────────────────────────────────
    prelim_frames: list[pd.DataFrame] = []
    for qd in quarter_dates:
        df = _fetch_preliminary(qd)
        time.sleep(1.0)
        if df is not None:
            cols = list(df.columns)
            code_col = _col(cols, "代码") or _col(cols, "股票代码")
            if code_col:
                df["ticker"] = df[code_col].apply(to_ticker)
            df["quarter"] = qd
            df["asof"] = today_str
            prelim_frames.append(df)

    if prelim_frames:
        combined = pd.concat(prelim_frames, ignore_index=True)
        _PRELIMINARY_OUT.parent.mkdir(parents=True, exist_ok=True)
        combined.to_parquet(_PRELIMINARY_OUT, index=False)
        total += len(combined)
        log.info("china preannounce: preliminary %d rows → %s", len(combined), _PRELIMINARY_OUT)
    else:
        log.info("china preannounce: preliminary empty for quarters %s", quarter_dates)

    return total


def main() -> int:
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    argparse.ArgumentParser(description="Fetch A-share earnings pre-announcements").parse_args()
    n = refresh()
    return 0 if n >= 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
