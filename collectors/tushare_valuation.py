"""Per-name A-share valuation snapshot — Tushare daily_basic (GATED, premium tier).

The whole-market PE/PB/turnover/market-cap snapshot for every listed name in ONE call
(``daily_basic`` @ 2000积分). This is the PER-NAME upgrade over the free whole-MARKET
valuation anchor (collectors/china_a_valuation, which is one row/day) — it lets
engine/china_crowding fire the per-name ``rich_valuation`` leg cross-sectionally instead of
only the market-wide fallback sentinel.

GATED: no-ops entirely unless ``TUSHARE_TOKEN`` is set (see collectors/tushare_client). The
free china_a_val anchor stays the fallback, so CI and the keyless build are unaffected.

data/tushare/valuation.parquet — one row per name:
  ticker, close, pe, pe_ttm, pb, ps_ttm, dv_ttm, turnover_rate, total_mv_yi, circ_mv_yi,
  pe_pctile, pb_pctile   (cross-sectional 0..100 percentile among names with a positive ratio),
  trade_date, asof

DISPLAY/CONTEXT-ONLY. Cross-sectional A-share value has a negative Sharpe
(research/CHINA_HK_STOCK_SIGNALS.md) — this is a richness backdrop + the crowding froth leg,
never a scored allocation axis.
"""
from __future__ import annotations

import logging

import pandas as pd

from lib import config
from collectors import tushare_client as tc

log = logging.getLogger("tushare_valuation")

OUT = config.data_dir() / "tushare" / "valuation.parquet"
_FIELDS = "ts_code,trade_date,close,turnover_rate,pe,pe_ttm,pb,ps_ttm,dv_ttm,total_mv,circ_mv"


def _pctile(s: pd.Series) -> pd.Series:
    """Cross-sectional 0..100 percentile, computed only over positive values (loss-making /
    missing ratios stay NaN — a negative PE is not "cheap")."""
    v = pd.to_numeric(s, errors="coerce")
    pos = v.where(v > 0)
    return pos.rank(pct=True) * 100.0


def refresh() -> int:
    """Bake the latest whole-market daily_basic snapshot. Gated + idempotent within a UTC day.
    Returns the number of names written (0 when gated off / unavailable). Never raises."""
    if not tc.enabled():
        return 0
    today = pd.Timestamp.utcnow().strftime("%Y-%m-%d")
    if OUT.exists():
        try:
            if str(pd.read_parquet(OUT, columns=["asof"])["asof"].max()) >= today:
                return 0
        except Exception:  # noqa: BLE001
            pass
    df, trade_date = tc.snapshot_by_date("daily_basic", fields=_FIELDS)
    if df is None or df.empty:
        log.warning("tushare valuation: no daily_basic snapshot")
        return 0
    df = df.rename(columns={"ts_code": "ticker"})
    for c in ("close", "pe", "pe_ttm", "pb", "ps_ttm", "dv_ttm", "turnover_rate", "total_mv", "circ_mv"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df["total_mv_yi"] = df["total_mv"] / 1e4 if "total_mv" in df.columns else None   # 万元 → 亿元
    df["circ_mv_yi"] = df["circ_mv"] / 1e4 if "circ_mv" in df.columns else None
    df["pe_pctile"] = _pctile(df["pe_ttm"]) if "pe_ttm" in df.columns else None
    df["pb_pctile"] = _pctile(df["pb"]) if "pb" in df.columns else None
    df["trade_date"] = trade_date
    df["asof"] = today
    keep = ["ticker", "close", "pe", "pe_ttm", "pb", "ps_ttm", "dv_ttm", "turnover_rate",
            "total_mv_yi", "circ_mv_yi", "pe_pctile", "pb_pctile", "trade_date", "asof"]
    out = df[[c for c in keep if c in df.columns]].dropna(subset=["ticker"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT, index=False)
    log.info("tushare valuation: wrote %s (%d names, %s)", OUT, len(out), trade_date)
    return len(out)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    return 0 if refresh() else 1


if __name__ == "__main__":
    raise SystemExit(main())
