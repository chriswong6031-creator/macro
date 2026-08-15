"""Broker monthly gold-stock picks (券商每月金股) — Tushare broker_recommend (GATED, premium).

Each month sell-side desks publish their top conviction picks ("金股"); ``broker_recommend``
returns (month, broker, ts_code, name) rows. Aggregated per name into a CONVICTION TALLY = how
many distinct brokers picked it this month — a clean, count-based sell-side conviction read
(China analyst RATINGS are ~97% "buy" and useless, but the discrete monthly pick list is not).

GATED: no-ops unless ``TUSHARE_TOKEN`` is set.

DISPLAY SNAPSHOT (unchanged contract):
  data/tushare/broker.parquet — one row per name:
  ticker, name, n_brokers, brokers (JSON list), month, asof
  Latest-month only; overwritten each successful fetch. Display surfaces keep reading this.

EVIDENCE STORE (append-only, keep-first):
  data/tushare/broker_hist.parquet — one row per (month, ticker, broker)
  first_seen is immutable. known_at is set ONLY when the vendor month equals the
  Asia/Shanghai collection calendar month (prospective). A historical-month re-fetch
  is stored with known_at UNKNOWN / pit_eligible=False and MUST NOT enter evidence
  studies. Month-start is never used as a known_at stamp.

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
from collectors import _first_seen_store as fss

log = logging.getLogger("tushare_broker")

OUT = config.data_dir() / "tushare" / "broker.parquet"
OUT_HIST = config.data_dir() / "tushare" / "broker_hist.parquet"
SOURCE = "tushare.broker_recommend"

HIST_COLUMNS = (
    "month",
    "ticker",
    "broker",
    "name",
    "first_seen",
    "fetched_at",
    "asof",
    "known_at",
    "pit_eligible",
    "schema_version",
    "source",
)
HIST_KEY = ["month", "ticker", "broker"]


def _recent_months(n: int = 3) -> list[str]:
    """The current + previous (n-1) months as YYYYMM, newest first."""
    out, dt = [], datetime.now(timezone.utc).replace(day=1)
    for _ in range(n):
        out.append(dt.strftime("%Y%m"))
        dt = (dt - timedelta(days=1)).replace(day=1)
    return out


def _collection_month(fetched_at: str) -> str:
    """Asia/Shanghai YYYYMM of the collection stamp — the vendor month is a China calendar month."""
    ts = pd.Timestamp(fetched_at)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    return ts.tz_convert("Asia/Shanghai").strftime("%Y%m")


def broker_pit_flags(month: str, fetched_at: str) -> tuple[bool, str]:
    """PIT-eligible only when vendor month == collection calendar month.

    Historical months are stored with known_at UNKNOWN. Month-start (or any other
    inferred date) is never returned as known_at.
    """
    month = str(month or "").strip()
    if month and month == _collection_month(fetched_at):
        return True, fetched_at
    return False, ""


def hist_rows_from_raw(df: pd.DataFrame, *, month: str, fetched_at: str,
                       asof: str) -> list[dict]:
    """One evidence row per (month, ticker, broker). Pure over the vendor frame."""
    pit_ok, known_at = broker_pit_flags(month, fetched_at)
    rows: list[dict] = []
    for _, r in df.iterrows():
        ticker = str(r.get("ticker") or "").strip()
        broker = str(r.get("broker") or "").strip()
        if not ticker or not broker:
            continue
        rows.append({
            "month": str(month),
            "ticker": ticker,
            "broker": broker,
            "name": str(r.get("name") or ""),
            "first_seen": fetched_at,
            "fetched_at": fetched_at,
            "asof": asof,
            "known_at": known_at,
            "pit_eligible": pit_ok,
            "schema_version": fss.SCHEMA_VERSION,
            "source": SOURCE,
        })
    return rows


def accrue_broker_hist(rows: list[dict]) -> int:
    """Append-only keep-first on (month, ticker, broker). Returns net-new keys."""
    return fss.accrue_keep_first(
        OUT_HIST, rows, columns=HIST_COLUMNS, key=HIST_KEY,
        sort_by=["month", "ticker", "broker"],
    )


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
    fetched_at = datetime.now(timezone.utc).isoformat()
    n_hist = accrue_broker_hist(hist_rows_from_raw(
        df, month=str(month), fetched_at=fetched_at, asof=today))
    rows: list[dict] = []
    for t, g in df.groupby("ticker"):
        brokers = sorted({str(b) for b in g["broker"].dropna()})
        nm = str(g["name"].dropna().iloc[0]) if g["name"].notna().any() else t
        rows.append({"ticker": str(t), "name": nm, "n_brokers": len(brokers),
                     "brokers": json.dumps(brokers, ensure_ascii=False), "month": month, "asof": today})
    out = pd.DataFrame(rows).sort_values("n_brokers", ascending=False)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT, index=False)
    log.info("tushare broker: wrote %s (%d names, month %s); hist +%d -> %s",
             OUT, len(out), month, n_hist, OUT_HIST)
    return len(out)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    return 0 if refresh() else 1


if __name__ == "__main__":
    raise SystemExit(main())
