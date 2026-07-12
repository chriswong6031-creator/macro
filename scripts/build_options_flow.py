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
from lib import config, nyse_calendar, store

log = logging.getLogger(__name__)
SUMMARY_KEYS = ("spot", "volume", "premium_mn", "net_premium_mn", "pc_ratio", "signed_pc",
                "zerodte_share", "gamma_flow_bn", "delta_flow_mn", "assumed_gex_bn",
                "fresh_contracts", "net_doi", "doi_pc")


def _chain_files() -> list[tuple[date, str]]:
    """Sorted (date, path) for every per-day snapshot chain parquet."""
    out = []
    for f in sorted(glob.glob(str(config.data_dir() / "polygon_gex" / "chains" / "*.parquet"))):
        stem = f.split("/")[-1].replace(".parquet", "")
        try:
            out.append((datetime.strptime(stem, "%Y-%m-%d").date(), f))
        except ValueError:
            continue
    return out


def _read_chain(path: str) -> pd.DataFrame:
    df = pd.read_parquet(path)
    if "strike_ticker" in df.columns:
        df = df.rename(columns={"strike_ticker": "ticker"})
    return df


def _chain_pair(d: date):
    """(today_df, today_date, prior_df, prior_date) for date d: the nearest snapshot file
    on/before d plus the immediately PRIOR distinct snapshot day (for the ΔOI positioning
    read). prior_* are None until a second OI snapshot day exists. Returns (None, ...) if
    no chains are stored yet."""
    files = _chain_files()
    if not files:
        return None, None, None, None
    pick_i = None
    for i, (fd, _f) in enumerate(files):             # nearest on/before d
        if fd <= d:
            pick_i = i
    if pick_i is None:
        pick_i = len(files) - 1                       # all newer than d -> use the latest
    today_date, today_path = files[pick_i]
    today = _read_chain(today_path)
    prior_df = prior_date = None
    if pick_i > 0:
        prior_date, prior_path = files[pick_i - 1]
        prior_df = _read_chain(prior_path)
    return today, today_date, prior_df, prior_date


def build() -> list[dict]:
    """Build the flow desk; returns the manifest rows (empty when no data)."""
    if not mf.enabled():
        log.info("options_flow: no MASSIVE_S3 creds — skip")
        return []
    from engine.options_universe import gex_symbols
    syms = gex_symbols((config.load().get("polygon", {}) or {}).get("gex"))
    if not syms:
        log.info("options_flow: no universe configured")
        return []
    log.info("options_flow: universe = %d underlyings", len(syms))
    d = mf.latest_available("minute")
    if d is None:
        log.info("options_flow: no entitled minute file in the recent window — skip")
        return []
    minute = mf.fetch_aggs(d, "minute", underlyings=syms)
    if minute.empty:
        log.warning("options_flow: minute file %s empty after filter", d)
        return []
    greeks, _gd, prior_chain, prior_date = _chain_pair(d)
    if prior_date is not None:
        log.info("options_flow: ΔOI positioning vs prior snapshot %s", prior_date)
    site = config.ROOT / config.load()["storage"]["site_dir"]
    out_dir = site / "flow"
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest, masters = [], {}
    for sym in syms:
        msub = minute[minute["underlying"] == sym]
        if msub.empty:
            continue
        g = spot = oi_today = prior_oi = None
        if greeks is not None:
            gsub = greeks[greeks["underlying"] == sym]
            if not gsub.empty:
                g = gsub[["ticker", "gamma", "delta", "oi"]]
                spot = float(gsub["spot"].iloc[0])
                # richer per-strike frame for the multi-day ΔOI positioning read
                oi_today = gsub[["ticker", "is_call", "K", "expiry", "oi", "delta"]].rename(
                    columns={"K": "strike"})
        if prior_chain is not None:
            psub = prior_chain[prior_chain["underlying"] == sym]
            if not psub.empty:
                prior_oi = psub[["ticker", "oi"]]
        payload = of.build_flow(sym, msub, g, spot, d,
                                oi_today=oi_today, prior_oi=prior_oi, prior_asof=prior_date)
        if not payload.get("available"):
            continue
        (out_dir / f"{sym}.json").write_text(json.dumps(payload, separators=(",", ":"), default=float))
        dealer = payload.get("dealer") or {}
        pos = payload.get("positioning") or {}
        row = {"key": sym, "asof": payload.get("asof"), "spot": payload.get("spot"),
               "net_premium_mn": payload.get("net_premium_mn"), "signed_pc": payload.get("signed_pc"),
               "zerodte_share": payload.get("zerodte_share"),
               "gamma_flow_bn": dealer.get("gamma_flow_bn"), "delta_flow_mn": dealer.get("delta_flow_mn"),
               "fresh_contracts": (payload.get("new_positions") or {}).get("fresh_contracts"),
               "net_doi": pos.get("net_doi") if pos.get("available") else None,
               "doi_pc": pos.get("doi_pc") if pos.get("available") else None,
               "positioning_lean": pos.get("lean_en") if pos.get("available") else None,
               "tone": (payload.get("verdict") or {}).get("tone"),
               "verdict": (payload.get("verdict") or {}).get("en")}
        manifest.append(row)
        masters[sym] = row
        # accrue a 1-row/day summary for the future calibration/validation gate
        try:
            srow = {k: (payload.get(k) if k in payload else dealer.get(k)
                        if k in dealer else (payload.get("new_positions") or {}).get(k)
                        if k in (payload.get("new_positions") or {})
                        else (payload.get("positioning") or {}).get(k))
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


def _check_staleness() -> None:
    """FC-R11: warn (never fail) when the newest summary row is older than the last NYSE session.

    Emits ::warning so GitHub Actions surfaces it in the annotation panel.
    Uses if/fi logic: only the warning message path has an exit code effect — never the check."""
    # Use AAPL as the representative ticker (always in universe)
    newest: date | None = store.last_date("options_flow", "summary_AAPL")
    if newest is None:
        log.info("options_flow staleness-check: no summary_AAPL row yet — skip")
        return
    try:
        expected = nyse_calendar.expected_last_session()
    except Exception as e:  # noqa: BLE001
        log.debug("options_flow staleness-check: calendar error %s — skip", e)
        return
    if newest < expected:
        import sys
        msg = (f"options_flow summary is stale: newest row={newest}, "
               f"expected last session={expected}. "
               f"Run scripts/backfill_options_flow.py or await the next nightly build.")
        print(f"::warning ::{msg}", file=sys.stderr)
        log.warning("options_flow: %s", msg)
    else:
        log.info("options_flow staleness-check: ok (newest=%s, expected=%s)", newest, expected)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    rows = build()
    log.info("options_flow: built %d names", len(rows))
    _check_staleness()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
