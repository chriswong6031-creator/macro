"""Per-name + sector money flow (资金流向) snapshot — Tushare DC feeds (GATED, premium tier).

THE gap-filler. The free Eastmoney push2 fund-flow endpoints 502 from a non-CN IP, so the
China desk had no working fund-flow signal at all. Tushare's DC (东方财富-sourced) endpoints
serve the exact same data, IP-reliably, in one whole-market call each (5000积分):

  moneyflow_dc      per-NAME    main-force net inflow (超大单 + 大单), net amount + rate
  moneyflow_ind_dc  per-SECTOR  industry net inflow + rank (东财 board level)

The per-name read becomes a NEW signed leg in the alt-data convergence (engine/china_altdata
``flow``); the sector read is collected for the divergence radar (sector-flow vs price). GATED:
no-ops unless ``TUSHARE_TOKEN`` is set; absent → the leg is simply omitted (never read as 0).

data/tushare/moneyflow.parquet (per name):
  ticker, name, close, pct_change, net_amount (万元), net_amount_rate (%),
  main_net (超大+大单净额, 万元), main_net_rate (%), trade_date, asof
data/tushare/moneyflow_sector.parquet (per 东财 industry board):
  sector_code, name, net_amount, net_amount_rate, content_type, rank, trade_date, asof

DISPLAY/CONTEXT-ONLY until china_validation proves a forward edge — a cross-sectional
agreement read, never a sizer.
"""
from __future__ import annotations

import logging

import pandas as pd

from lib import config
from collectors import tushare_client as tc

log = logging.getLogger("tushare_moneyflow")

OUT = config.data_dir() / "tushare" / "moneyflow.parquet"
OUT_SECTOR = config.data_dir() / "tushare" / "moneyflow_sector.parquet"
_FIELDS = ("trade_date,ts_code,name,pct_change,close,net_amount,net_amount_rate,"
           "buy_elg_amount,buy_elg_amount_rate,buy_lg_amount,buy_lg_amount_rate")
_FIELDS_IND = "trade_date,content_type,ts_code,name,net_amount,net_amount_rate,rank"


def _num_cols(df: pd.DataFrame, cols) -> None:
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")


def _scol(df: pd.DataFrame, name: str) -> pd.Series:
    """A numeric Series for `name`, or an all-zero Series when Tushare dropped that tier-field
    (df.get(name, 0) would return a scalar int 0, and 0.fillna() raises)."""
    return df[name].fillna(0) if name in df.columns else pd.Series(0.0, index=df.index)


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
    df, trade_date = tc.snapshot_by_date("moneyflow_dc", fields=_FIELDS)
    if df is None or df.empty:
        log.warning("tushare moneyflow: no moneyflow_dc snapshot")
        return 0
    _num_cols(df, ["pct_change", "close", "net_amount", "net_amount_rate",
                   "buy_elg_amount", "buy_elg_amount_rate", "buy_lg_amount", "buy_lg_amount_rate"])
    df["ticker"] = df["ts_code"]
    # main-force = 超大单 (elg) + 大单 (lg) net — the "smart money" leg (Series-safe if a tier-field is absent)
    df["main_net"] = _scol(df, "buy_elg_amount") + _scol(df, "buy_lg_amount")
    df["main_net_rate"] = _scol(df, "buy_elg_amount_rate") + _scol(df, "buy_lg_amount_rate")
    df["trade_date"] = trade_date
    df["asof"] = today
    keep = ["ticker", "name", "close", "pct_change", "net_amount", "net_amount_rate",
            "main_net", "main_net_rate", "trade_date", "asof"]
    out = df[[c for c in keep if c in df.columns]].dropna(subset=["ticker"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT, index=False)
    log.info("tushare moneyflow: wrote %s (%d names, %s)", OUT, len(out), trade_date)

    # sector board flow (best-effort; absent just leaves the radar without the leg)
    try:
        sdf, sdate = tc.snapshot_by_date("moneyflow_ind_dc", fields=_FIELDS_IND)
        if sdf is not None and len(sdf):
            _num_cols(sdf, ["net_amount", "net_amount_rate", "rank"])
            sdf = sdf.rename(columns={"ts_code": "sector_code"})
            sdf["trade_date"] = sdate
            sdf["asof"] = today
            skeep = ["sector_code", "name", "net_amount", "net_amount_rate",
                     "content_type", "rank", "trade_date", "asof"]
            sdf[[c for c in skeep if c in sdf.columns]].to_parquet(OUT_SECTOR, index=False)
            log.info("tushare moneyflow sector: wrote %s (%d boards)", OUT_SECTOR, len(sdf))
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("tushare moneyflow sector skipped (%s)", e)
    return len(out)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    return 0 if refresh() else 1


if __name__ == "__main__":
    raise SystemExit(main())
