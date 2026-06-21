"""Broker monthly gold-stock picks (券商每月金股) — Tushare broker_recommend (GATED, premium).

Each month sell-side desks publish their top conviction picks ("金股"); ``broker_recommend``
returns (month, broker, ts_code, name) rows. Aggregated per name into a CONVICTION TALLY = how
many distinct brokers picked it this month — a clean, count-based sell-side conviction read
(China analyst RATINGS are ~97% "buy" and useless, but the discrete monthly pick list is not).

GATED: no-ops unless ``TUSHARE_TOKEN`` is set. data/tushare/broker.parquet — one row per name:
  ticker, name, n_brokers, brokers (JSON list), month, asof

DISPLAY/CONTEXT-ONLY (registered ``display`` in china_signal_lab — surfaced as the 券商金股 panel on
the alt-data desk) — a pick-count backdrop; never scored into the convergence.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

import pandas as pd

from lib import config
from collectors import tushare_client as tc

log = logging.getLogger("tushare_broker")

OUT = config.data_dir() / "tushare" / "broker.parquet"


def _recent_months(n: int = 3) -> list[str]:
    """The current + previous (n-1) months as YYYYMM, newest first."""
    out, dt = [], datetime.now(timezone.utc).replace(day=1)
    for _ in range(n):
        out.append(dt.strftime("%Y%m"))
        dt = (dt - timedelta(days=1)).replace(day=1)
    return out


def refresh() -> int:
    if not tc.enabled():
        return 0
    today = pd.Timestamp.utcnow().strftime("%Y-%m-%d")
    if OUT.exists():
        try:
            if str(pd.read_parquet(OUT, columns=["asof"])["asof"].max()) >= today:
                return 0
        except Exception:  # noqa: BLE001
            pass
    df = month = None
    for m in _recent_months():                 # newest month that actually has picks
        d = tc.query("broker_recommend", month=m, fields="month,broker,ts_code,name")
        if d is not None and len(d):
            df, month = d, m
            break
    if df is None or df.empty:
        log.warning("tushare broker: no broker_recommend rows")
        return 0
    df = df.rename(columns={"ts_code": "ticker"}).dropna(subset=["ticker"])
    rows: list[dict] = []
    for t, g in df.groupby("ticker"):
        brokers = sorted({str(b) for b in g["broker"].dropna()})
        nm = str(g["name"].dropna().iloc[0]) if g["name"].notna().any() else t
        rows.append({"ticker": str(t), "name": nm, "n_brokers": len(brokers),
                     "brokers": json.dumps(brokers, ensure_ascii=False), "month": month, "asof": today})
    out = pd.DataFrame(rows).sort_values("n_brokers", ascending=False)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT, index=False)
    log.info("tushare broker: wrote %s (%d names, month %s)", OUT, len(out), month)
    return len(out)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    return 0 if refresh() else 1


if __name__ == "__main__":
    raise SystemExit(main())
