"""Per-name margin (融资融券) snapshot — Tushare margin_detail (GATED, premium tier).

Whole-market per-name financing/short balances for the latest day in ONE call
(``margin_detail`` @ 2000积分) — a cleaner, IP-reliable per-name 融资余额 than the free
akshare feed. engine/china_crowding prefers this for the ``margin_froth`` leg (a surging
financing balance is the 2015 fire-sale crowding mechanism), falling back to the free
collectors/china_margin_detail cache when the token is absent.

GATED: no-ops unless ``TUSHARE_TOKEN`` is set.

DISPLAY SNAPSHOT (unchanged contract):
  data/tushare/margin.parquet — one row per name:
  ticker, fin_balance (融资余额, 元), short_balance (融券余额), total_balance (融资融券余额),
  fin_buy (融资买入额), fin_pctile (cross-sectional 0..100 of fin_balance), trade_date, asof
  Latest trade_date only; overwritten each successful fetch.

EVIDENCE STORE (append-only, keep-first):
  data/tushare/margin_hist.parquet — one row per (ticker, trade_date)
  Vendor trade_date is preserved separately from first_seen / fetched_at. A re-fetch
  of the same (ticker, trade_date) cannot move first_seen or rewrite the first payload.
  Cross-sectional fin_pctile is snapshot-only (it is a function of that day's universe)
  and is not stored as evidence.

DISPLAY/CONTEXT-ONLY — leverage positioning backdrop, not a scored axis.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd

from lib import config
from collectors import tushare_client as tc
from collectors import _first_seen_store as fss

log = logging.getLogger("tushare_margin")

OUT = config.data_dir() / "tushare" / "margin.parquet"
OUT_HIST = config.data_dir() / "tushare" / "margin_hist.parquet"
SOURCE = "tushare.margin_detail"
_FIELDS = "trade_date,ts_code,rzye,rqye,rzmre,rzrqye"

HIST_COLUMNS = (
    "ticker",
    "trade_date",
    "fin_balance",
    "short_balance",
    "fin_buy",
    "total_balance",
    "first_seen",
    "fetched_at",
    "asof",
    "schema_version",
    "source",
)
HIST_KEY = ["ticker", "trade_date"]


def hist_rows_from_snapshot(df: pd.DataFrame, *, trade_date: str,
                            fetched_at: str, asof: str) -> list[dict]:
    """One evidence row per (ticker, trade_date). Pure over the snapshot frame."""
    rows: list[dict] = []
    for _, r in df.iterrows():
        ticker = str(r.get("ticker") or "").strip()
        if not ticker:
            continue
        rows.append({
            "ticker": ticker,
            "trade_date": str(trade_date),
            "fin_balance": r.get("fin_balance"),
            "short_balance": r.get("short_balance"),
            "fin_buy": r.get("fin_buy"),
            "total_balance": r.get("total_balance"),
            "first_seen": fetched_at,
            "fetched_at": fetched_at,
            "asof": asof,
            "schema_version": fss.SCHEMA_VERSION,
            "source": SOURCE,
        })
    return rows


def accrue_margin_hist(rows: list[dict]) -> int:
    """Append-only keep-first on (ticker, trade_date). Returns net-new keys."""
    return fss.accrue_keep_first(
        OUT_HIST, rows, columns=HIST_COLUMNS, key=HIST_KEY,
        sort_by=["trade_date", "ticker"],
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
    df, trade_date = tc.snapshot_by_date("margin_detail", fields=_FIELDS)
    if df is None or df.empty:
        log.warning("tushare margin: no margin_detail snapshot")
        return 0
    df = df.rename(columns={"ts_code": "ticker", "rzye": "fin_balance", "rqye": "short_balance",
                            "rzmre": "fin_buy", "rzrqye": "total_balance"})
    for c in ("fin_balance", "short_balance", "fin_buy", "total_balance"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df["fin_pctile"] = df["fin_balance"].rank(pct=True) * 100.0 if "fin_balance" in df.columns else None
    df["trade_date"] = trade_date
    df["asof"] = today
    keep = ["ticker", "fin_balance", "short_balance", "fin_buy", "total_balance",
            "fin_pctile", "trade_date", "asof"]
    out = df[[c for c in keep if c in df.columns]].dropna(subset=["ticker"])
    fetched_at = datetime.now(timezone.utc).isoformat()
    n_hist = accrue_margin_hist(hist_rows_from_snapshot(
        out, trade_date=str(trade_date), fetched_at=fetched_at, asof=today))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT, index=False)
    log.info("tushare margin: wrote %s (%d names, %s); hist +%d -> %s",
             OUT, len(out), trade_date, n_hist, OUT_HIST)
    return len(out)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    return 0 if refresh() else 1


if __name__ == "__main__":
    raise SystemExit(main())
