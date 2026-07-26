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
from collectors import _drip
from collectors import tushare_client as tc

log = logging.getLogger("tushare_moneyflow")

OUT = config.data_dir() / "tushare" / "moneyflow.parquet"
OUT_SECTOR = config.data_dir() / "tushare" / "moneyflow_sector.parquet"
# Append-only PIT history files — existing consumers keep reading the snapshot files above.
OUT_HIST = config.data_dir() / "tushare" / "moneyflow_hist.parquet"
OUT_SECTOR_HIST = config.data_dir() / "tushare" / "moneyflow_sector_hist.parquet"
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


def _committed_through() -> str:
    """Data-through date of the parquet already on disk, for the loud-failure log line.

    Best-effort and never raises — this only ever decorates a warning message."""
    try:
        if not OUT.exists():
            return "absent"
        s = pd.read_parquet(OUT, columns=["trade_date"])["trade_date"]
        return str(s.max()) if len(s) else "empty"
    except Exception:  # noqa: BLE001 — a decoration must never mask the real failure
        return "unreadable"


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
        # LOUD fail-soft: name the ENDPOINT and the consequence (the committed plane stops
        # advancing) on one line, so a multi-day freeze is greppable instead of silent.
        # tushare_client.query() has already logged the vendor's own code/msg immediately
        # above this — 40101 = bad/rotated token, 40203 = rate-limit, 40203+权限 = not
        # entitled. Still returns 0 and never raises: a dead feed must not break the build.
        log.warning("tushare moneyflow: endpoint moneyflow_dc returned no snapshot — %s NOT "
                    "advanced, committed plane still through %s. See the tushare_client "
                    "warning above for the vendor code (40101=bad/rotated token, "
                    "40203=rate-limit/entitlement).", OUT.name, _committed_through())
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
    # Append to the PIT per-name history (additive; existing consumers keep reading OUT).
    try:
        _drip.append_snapshot(OUT_HIST, out.to_dict("records"), date_col="asof")
        log.info("tushare moneyflow: appended history %s (asof %s)", OUT_HIST, today)
    except Exception as e:  # noqa: BLE001 — history is telemetry, never fatal
        log.warning("tushare moneyflow: name history append failed (%s)", e)

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
            sout = sdf[[c for c in skeep if c in sdf.columns]]
            sout.to_parquet(OUT_SECTOR, index=False)
            log.info("tushare moneyflow sector: wrote %s (%d boards)", OUT_SECTOR, len(sout))
            # Append to the PIT sector history (additive).
            # _drip.append_snapshot dedupes on (date_col, "ticker"); alias sector_code
            # → ticker in the history-only copy so the natural key is always present.
            try:
                sout_h = sout.copy()
                sout_h["ticker"] = sout_h["sector_code"]
                _drip.append_snapshot(OUT_SECTOR_HIST, sout_h.to_dict("records"), date_col="asof")
                log.info("tushare moneyflow: appended sector history %s (asof %s)",
                         OUT_SECTOR_HIST, today)
            except Exception as se:  # noqa: BLE001 — history is telemetry, never fatal
                log.warning("tushare moneyflow: sector history append failed (%s)", se)
        else:
            # Was a SILENT skip: an empty moneyflow_ind_dc left the sector radar frozen with
            # nothing in the log at all. Loud fail-soft — the per-name leg above still stands.
            log.warning("tushare moneyflow: endpoint moneyflow_ind_dc returned no snapshot — "
                        "%s NOT advanced (sector radar keeps its previous rows)",
                        OUT_SECTOR.name)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("tushare moneyflow sector skipped (%s)", e)
    return len(out)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    return 0 if refresh() else 1


if __name__ == "__main__":
    raise SystemExit(main())
