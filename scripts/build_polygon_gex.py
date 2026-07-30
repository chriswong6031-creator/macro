"""Polygon options-OI accrual — the GEX FOUNDATION (display / research only).

Each run snapshots the configured underlyings' option chains via Polygon and:
  1. writes the RAW per-strike chain to data/polygon_gex/chains/{YYYY-MM-DD}.parquet
     — date-partitioned & append-only (never rewrites history, so the daily
     ``git add data/`` adds exactly one small blob). This is the per-strike OI
     history the Cboe path discards and that CANNOT be backfilled: open interest is
     point-in-time only.
  2. upserts a per-underlying compute_gex summary to data/polygon_gex/summary_{SYM}
     .parquet (1 row/day, mirroring the Cboe gex_{SYM} frames so the two sources are
     directly comparable; feeds the future validate-gated GEX drawdown leg).

No-op without POLYGON_API_KEY. Never raises into the caller — collect.py wraps this
additively, exactly like the FRED-vintages / basket-extras steps. See
collectors/polygon_options.py and engine/gex_engine.py.
"""
from __future__ import annotations

import argparse
import logging
from datetime import date, datetime, timezone

import pandas as pd

from collectors.polygon_options import PolygonOptions
from engine.gex_engine import compute_gex
from lib import config, store, nyse_calendar

log = logging.getLogger(__name__)

GROUP = "polygon_gex"
# the compute_gex summary fields persisted per underlying (matches cboe GexAdapter._row)
SUMMARY_KEYS = ("spot", "net_gex_bn", "net_vex", "net_cex", "gamma_flip",
                "dist_to_flip_pct", "gamma_regime", "magnet_up", "magnet_down",
                "charm_anchor", "charm_net_sign", "iv30", "put_call_oi_ratio",
                "max_pain", "n_strikes", "tier")


def _as_date(x) -> date:
    if isinstance(x, datetime):
        return x.date()
    if isinstance(x, date):
        return x
    return datetime.now(timezone.utc).date()


def _chains_dir():
    d = config.data_dir() / GROUP / "chains"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _compact(raw: pd.DataFrame) -> pd.DataFrame:
    """Shrink the daily raw file (it commits every run): float32 numerics + a
    categorical underlying ~halve it with no analytical cost (float32's ~16M-int
    precision covers any OI)."""
    out = raw.copy()
    for c in ("K", "T", "oi", "iv", "gamma", "delta", "volume", "spot"):
        if c in out.columns:
            out[c] = out[c].astype("float32")
    out["underlying"] = out["underlying"].astype("category")
    return out


def _summarize(raw: pd.DataFrame, sym: str, cfg: dict) -> pd.DataFrame | None:
    """compute_gex over one underlying's stored chain -> 1-row/day summary frame.
    Returns None when the chain has no iv-bearing strikes to trust."""
    sub = raw[raw["underlying"] == sym].dropna(subset=["iv"])
    if sub.empty:
        return None
    spot = float(sub["spot"].iloc[0])
    gx = cfg["gex"]
    ecfg = {k: gx[k] for k in ("contract_multiplier", "pct_move",
                               "strike_window_pct", "max_expiry_days") if k in gx}
    ecfg["r"] = gx.get("r", 0.043)
    ecfg["q"] = (cfg.get("div_yield") or {}).get(sym, 0.0)
    summ = compute_gex(sub[["K", "T", "iv", "oi", "is_call", "expiry"]], spot, ecfg, symbol=sym)
    asof = pd.Timestamp(sub["asof"].iloc[0]).normalize()
    return pd.DataFrame({k: [summ.get(k)] for k in SUMMARY_KEYS}, index=[asof])


def accrue(as_of=None) -> dict:
    """Snapshot + persist for one day. Returns a small status dict (logging/tests)."""
    cfg = config.load().get("polygon")
    if not cfg:
        log.info("polygon: no config section — skip")
        return {"status": "no_config"}
    client = PolygonOptions()
    if not client.enabled():
        log.info("polygon: POLYGON_API_KEY absent — skip (no-op)")
        return {"status": "no_key"}

    asof = _as_date(as_of)
    from engine.options_universe import gex_symbols
    symbols = gex_symbols(cfg.get("gex"))
    log.info("polygon: snapshotting %d underlyings (%d anchors + baskets=%s)",
             len(symbols), len(cfg["gex"].get("symbols") or []),
             cfg["gex"].get("include_baskets", False))
    # WRITE-SIDE SESSION GATE (M7, review 2026-07-29). The chains directory carried 11
    # non-session snapshot FILES of 39, and the per-underlying summaries ~11 non-session
    # dates of 39. A snapshot taken when the market never opened re-records the previous
    # session's OI/volume off a stale spot, then enters every reader as a duplicate day:
    # altdata.unusual_options counted it as both "today" and part of its own baseline,
    # options_stamp's ΔOI window lost a real session to it, and iv_rank's n_obs inflated.
    # Readers all session-filter now, so historical files stay put — this stops NEW ones.
    if not nyse_calendar.is_session(asof):
        # Bare line-start print (never a logger — see tests/test_gh_annotation_line_start).
        print(f"::notice title=polygon-session-gate::{asof} is not an NYSE session - "
              f"chain snapshot and summaries skipped, store left unadvanced", flush=True)
        log.info("polygon: %s is not a trading session — nothing accrued", asof)
        return {"status": "non_session", "date": asof.isoformat()}

    raw = client.snapshot(symbols, asof)
    if raw.empty:
        log.warning("polygon: snapshot empty — nothing accrued")
        return {"status": "empty", "date": asof.isoformat()}

    # 1. raw per-strike chain, date-partitioned (append-only, git-friendly)
    path = _chains_dir() / f"{asof.isoformat()}.parquet"
    _compact(raw).to_parquet(path)
    log.info("polygon: wrote raw chain %s (%d rows, %d underlyings)",
             path.name, len(raw), raw["underlying"].nunique())

    # 2. per-underlying compute_gex summary (reuse the engine — no new math)
    n_summ = 0
    for sym in symbols:
        try:
            row = _summarize(raw, sym, cfg)
            if row is not None:
                store.upsert(GROUP, f"summary_{sym}", row, outlier_col=None)
                n_summ += 1
        except Exception as e:  # noqa: BLE001 — one symbol must not abort the rest
            log.warning("polygon summary %s failed: %s", sym, e)

    return {"status": "ok", "rows": int(len(raw)),
            "underlyings": int(raw["underlying"].nunique()),
            "summaries": n_summ, "date": asof.isoformat()}


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="", help="YYYY-MM-DD (default: today UTC)")
    args = ap.parse_args()
    asof = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else None
    log.info("polygon accrual: %s", accrue(asof))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
