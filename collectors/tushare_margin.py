"""Per-name margin (融资融券) snapshot — Tushare margin_detail (GATED, premium tier).

Whole-market per-name financing/short balances for the latest day in ONE call
(``margin_detail`` @ 2000积分) — a cleaner, IP-reliable per-name 融资余额 than the free
akshare feed. engine/china_crowding prefers this for the ``margin_froth`` leg (a surging
financing balance is the 2015 fire-sale crowding mechanism), falling back to the free
collectors/china_margin_detail cache when the token is absent.

GATED: no-ops unless ``TUSHARE_TOKEN`` is set. data/tushare/margin.parquet — one row per name:
  ticker, fin_balance (融资余额, 元), short_balance (融券余额), total_balance (融资融券余额),
  fin_buy (融资买入额), fin_pctile (cross-sectional 0..100 of fin_balance), trade_date, asof

DISPLAY/CONTEXT-ONLY — leverage positioning backdrop, not a scored axis.
"""
from __future__ import annotations

import logging

import pandas as pd

from lib import config
from collectors import tushare_client as tc

log = logging.getLogger("tushare_margin")

OUT = config.data_dir() / "tushare" / "margin.parquet"
_FIELDS = "trade_date,ts_code,rzye,rqye,rzmre,rzrqye"


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
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT, index=False)
    log.info("tushare margin: wrote %s (%d names, %s)", OUT, len(out), trade_date)
    return len(out)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    return 0 if refresh() else 1


if __name__ == "__main__":
    raise SystemExit(main())
