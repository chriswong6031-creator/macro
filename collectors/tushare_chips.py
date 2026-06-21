"""Per-name chip distribution / win-rate snapshot — Tushare cyq_perf (GATED, premium tier).

Eastmoney's 每日筹码及胜率 (chip cost-basis + winner-rate) for every name in one whole-market
call (``cyq_perf`` @ 5000积分). ``winner_rate`` = the % of float currently sitting in profit
(holder positioning) and ``weight_avg`` = the volume-weighted average holding cost — a rigorous,
backfilled-to-2018 upgrade over the 千股千评 main-force-cost approximation.

GATED: no-ops unless ``TUSHARE_TOKEN`` is set. data/tushare/chips.parquet — one row per name:
  ticker, winner_rate (获利比例 %), weight_avg (加权平均成本), cost_50pct (中位成本),
  cost_5pct, cost_95pct, his_low, his_high, trade_date, asof

DISPLAY/CONTEXT-ONLY (registered ``pending`` in china_signal_lab) — collected + accruing via the
china_extras.chips() parser; not yet surfaced or scored, awaiting a Phase-0 validation.
"""
from __future__ import annotations

import logging

import pandas as pd

from lib import config
from collectors import tushare_client as tc

log = logging.getLogger("tushare_chips")

OUT = config.data_dir() / "tushare" / "chips.parquet"
_FIELDS = "ts_code,trade_date,his_low,his_high,cost_5pct,cost_50pct,cost_95pct,weight_avg,winner_rate"


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
    df, trade_date = tc.snapshot_by_date("cyq_perf", fields=_FIELDS)
    if df is None or df.empty:
        log.warning("tushare chips: no cyq_perf snapshot")
        return 0
    df = df.rename(columns={"ts_code": "ticker"})
    for c in ("his_low", "his_high", "cost_5pct", "cost_50pct", "cost_95pct", "weight_avg", "winner_rate"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df["trade_date"] = trade_date
    df["asof"] = today
    keep = ["ticker", "winner_rate", "weight_avg", "cost_50pct", "cost_5pct", "cost_95pct",
            "his_low", "his_high", "trade_date", "asof"]
    out = df[[c for c in keep if c in df.columns]].dropna(subset=["ticker"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT, index=False)
    log.info("tushare chips: wrote %s (%d names, %s)", OUT, len(out), trade_date)
    return len(out)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    return 0 if refresh() else 1


if __name__ == "__main__":
    raise SystemExit(main())
