"""scripts/build_options_flow.py — the daily OPTIONS FLOW desk (measured dealer positioning).

Pulls the freshest entitled OPRA minute-aggregate flat file (collectors/massive_flatfiles),
joins it to the per-contract greeks + open-interest we already snapshot (data/polygon_gex),
and runs engine/options_flow to MEASURE dealer positioning from the actual day's signed
volume — replacing the long-call/short-put ASSUMPTION. Writes:

  • site/flow/<KEY>.json   — full per-underlying flow payload (premium/PC/0DTE, measured
                             dealer gamma+delta FLOW, divergence-from-assumption, new positions)
  • site/flow/index.json   — manifest row per name (for a board)
  • site/flow/mastermind.json — compact context block for the bot
  • data/options_flow/summary_<KEY>.parquet — 1 row/day accrual (for the future
                             calibration/validation gate)

Universe = the names we snapshot greeks for (config polygon.gex.symbols), since the MEASURED
dealer read needs greeks. Graceful: no S3 creds / no minute file / no snapshot -> writes
nothing and returns 0 (never breaks the daily build). Signing is the minute tick-rule (no NBBO
on our plan); honesty carried in the payload. See engine/options_flow.py.

Run: .venv/bin/python -m scripts.build_options_flow
"""
from __future__ import annotations

import glob
import json
import logging
from datetime import date, datetime, timezone

import pandas as pd

from collectors import massive_flatfiles as mf
from engine import options_flow as of
from lib import config, store

log = logging.getLogger(__name__)
SUMMARY_KEYS = ("spot", "volume", "premium_mn", "net_premium_mn", "pc_ratio", "signed_pc",
                "zerodte_share", "gamma_flow_bn", "delta_flow_mn", "assumed_gex_bn",
                "fresh_contracts")


def _greeks_for(d: date) -> pd.DataFrame | None:
    """Per-contract greeks/OI/spot from the snapshot chain for date d (or the nearest
    earlier file). Returns a frame with ticker/underlying/gamma/delta/oi/spot."""
    files = sorted(glob.glob(str(config.data_dir() / "polygon_gex" / "chains" / "*.parquet")))
    if not files:
        return None
    pick = None
    for f in files:                                  # nearest file on/before d
        stem = f.split("/")[-1].replace(".parquet", "")
        try:
            fd = datetime.strptime(stem, "%Y-%m-%d").date()
        except ValueError:
            continue
        if fd <= d:
            pick = f
    pick = pick or files[-1]
    df = pd.read_parquet(pick)
    if "strike_ticker" in df.columns:
        df = df.rename(columns={"strike_ticker": "ticker"})
    return df


def build() -> list[dict]:
    """Build the flow desk; returns the manifest rows (empty when no data)."""
    if not mf.enabled():
        log.info("options_flow: no MASSIVE_S3 creds — skip")
        return []
    syms = list((config.load().get("polygon", {}).get("gex", {}) or {}).get("symbols") or [])
    if not syms:
        log.info("options_flow: no universe configured")
        return []
    d = mf.latest_available("minute")
    if d is None:
        log.info("options_flow: no entitled minute file in the recent window — skip")
        return []
    minute = mf.fetch_aggs(d, "minute", underlyings=syms)
    if minute.empty:
        log.warning("options_flow: minute file %s empty after filter", d)
        return []
    greeks = _greeks_for(d)
    site = config.ROOT / config.load()["storage"]["site_dir"]
    out_dir = site / "flow"
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest, masters = [], {}
    for sym in syms:
        msub = minute[minute["underlying"] == sym]
        if msub.empty:
            continue
        g = spot = None
        if greeks is not None:
            gsub = greeks[greeks["underlying"] == sym]
            if not gsub.empty:
                g = gsub[["ticker", "gamma", "delta", "oi"]]
                spot = float(gsub["spot"].iloc[0])
        payload = of.build_flow(sym, msub, g, spot, d)
        if not payload.get("available"):
            continue
        (out_dir / f"{sym}.json").write_text(json.dumps(payload, separators=(",", ":"), default=float))
        dealer = payload.get("dealer") or {}
        row = {"key": sym, "asof": payload.get("asof"), "spot": payload.get("spot"),
               "net_premium_mn": payload.get("net_premium_mn"), "signed_pc": payload.get("signed_pc"),
               "zerodte_share": payload.get("zerodte_share"),
               "gamma_flow_bn": dealer.get("gamma_flow_bn"), "delta_flow_mn": dealer.get("delta_flow_mn"),
               "fresh_contracts": (payload.get("new_positions") or {}).get("fresh_contracts"),
               "tone": (payload.get("verdict") or {}).get("tone"),
               "verdict": (payload.get("verdict") or {}).get("en")}
        manifest.append(row)
        masters[sym] = row
        # accrue a 1-row/day summary for the future calibration/validation gate
        try:
            srow = {k: (payload.get(k) if k in payload else dealer.get(k)
                        if k in dealer else (payload.get("new_positions") or {}).get(k))
                    for k in SUMMARY_KEYS}
            sdf = pd.DataFrame({k: [srow.get(k)] for k in SUMMARY_KEYS},
                               index=[pd.Timestamp(d)])
            store.upsert("options_flow", f"summary_{sym}", sdf, outlier_col=None)
        except Exception as e:  # noqa: BLE001 — accrual is additive
            log.warning("options_flow: summary %s failed: %s", sym, e)
        log.info("options_flow: %s net=$%sM gamma_flow=%s 0DTE=%s%%", sym,
                 row["net_premium_mn"], row["gamma_flow_bn"],
                 round((row["zerodte_share"] or 0) * 100))

    if manifest:
        (out_dir / "index.json").write_text(json.dumps(
            {"asof": str(d), "built": str(date.today()), "rows": manifest},
            separators=(",", ":"), default=float))
        (out_dir / "mastermind.json").write_text(json.dumps({
            "schema": "options_flow.context.v1", "asof": str(d),
            "signing": "minute tick-rule (no NBBO) — approximate, Databento-calibratable",
            "names": masters}, separators=(",", ":"), default=float))
    return manifest


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    rows = build()
    log.info("options_flow: built %d names", len(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
