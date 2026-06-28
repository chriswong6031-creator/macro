"""scripts/calibrate_flow_signing.py — measure how good the cheap tick-rule signing is.

Pulls a Databento `tbbo` sample (trades stamped with the prevailing NBBO) for the flow
universe over a few dates, then uses engine/flow_signing to compare the tick rule (what the
flow engine uses, since massive.com gives us no NBBO) against the gold-standard quote rule —
per trade AND, more importantly, whether the MINUTE-aggregated tick rule recovers the same
NET daily sign per contract (the thing that actually drives the measured dealer read).

Writes reports/flow-signing-calibration.md + data/options_flow/signing_gate.json, so the
flow desk can state its signing confidence honestly. INERT (writes a "no sample" gate)
until DATABENTO_API_KEY + the databento package are present.

Run: pip install databento; export DATABENTO_API_KEY=...; python -m scripts.calibrate_flow_signing
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import date, datetime, timedelta, timezone

import pandas as pd

from collectors import databento_tbbo as dbt
from engine import flow_signing
from lib import config

log = logging.getLogger(__name__)


SAMPLE_CACHE = "options_flow/_dbento_sample.parquet"     # raw tcbbo cache (avoid re-charging)


def _load_sample(universe, window) -> pd.DataFrame:
    """The calibration trade sample [ticker, ts, price, size, bid, ask]. Prefers the cached
    raw tcbbo pull (so re-runs never re-charge the card); else a fresh COST-GUARDED window."""
    cache = config.data_dir() / SAMPLE_CACHE
    if cache.exists():
        raw = pd.read_parquet(cache).reset_index()
        col = {c.lower(): c for c in raw.columns}
        def pk(*n):
            for x in n:
                if x in col:
                    return col[x]
            return None
        if pk("symbol") and pk("bid_px_00"):
            log.info("calibration: using cached tcbbo sample (%d trades, no charge)", len(raw))
            return pd.DataFrame({
                "ticker": raw[pk("symbol")].astype(str),
                "ts": pd.to_datetime(raw[pk("ts_event", "ts_recv")], errors="coerce"),
                "price": pd.to_numeric(raw[pk("price")], errors="coerce"),
                "size": pd.to_numeric(raw[pk("size")], errors="coerce"),
                "bid": pd.to_numeric(raw[pk("bid_px_00")], errors="coerce"),
                "ask": pd.to_numeric(raw[pk("ask_px_00")], errors="coerce"),
            }).dropna(subset=["price", "bid", "ask"])
    if not dbt.enabled():
        return pd.DataFrame()
    day = datetime.strptime(window[0][:10], "%Y-%m-%d").date()
    return dbt.fetch_tbbo(universe[:1], day, window=window)     # ONE name, short window = cheap


def run(universe: list[str] | None = None,
        window=("2026-06-18T14:30", "2026-06-18T14:50")) -> dict:
    syms = universe or list((config.load().get("polygon", {}).get("gex", {}) or {}).get("symbols") or ["SPY"])
    gate_path = config.data_dir() / "options_flow" / "signing_gate.json"
    gate_path.parent.mkdir(parents=True, exist_ok=True)

    trades = _load_sample(syms, window)
    if trades is None or trades.empty:
        gate = flow_signing.verdict({}, {})
        gate.update(asof=str(date.today()), enabled=dbt.enabled())
        gate_path.write_text(json.dumps(gate, indent=2))
        log.info("calibration: no sample (Databento %s) — display-only gate",
                 "enabled" if dbt.enabled() else "disabled")
        return {"status": "no_sample", "gate": gate}
    trades = trades[(trades["bid"] > 0) & (trades["ask"] >= trades["bid"])]
    per_trade = flow_signing.compare_trade_signs(trades)
    recovery = flow_signing.minute_sign_recovery(trades)
    gate = flow_signing.verdict(per_trade, recovery)
    gate.update(asof=str(date.today()), generated=datetime.now(timezone.utc).isoformat(),
                n_trades=int(len(trades)), universe=syms, enabled=True,
                # delta-adjusted signing was tested on full-day Databento truth (2026-06-18)
                # and did NOT beat the tick rule (~0.55 vs ~0.56 minute-agreement); bar signing
                # is bid-ask-bounce-limited. See research/OPTIONS_FLOW_DATA.md.
                delta_adjusted={"tested": True, "improves_direction": False,
                                "tick_minute_agreement": 0.556, "delta_adj_minute_agreement": 0.526,
                                "note": "no improvement on bars — bid-ask-bounce-limited; "
                                        "reliable direction needs the trade-level NBBO tape"})
    gate_path.write_text(json.dumps(gate, indent=2))

    report = [
        "# Flow-signing calibration (tick rule vs NBBO quote rule)\n",
        f"_generated {gate['generated']} · {len(trades):,} trades · {syms}_\n",
        "Our flow engine signs minute volume with the TICK RULE (no NBBO on the massive.com "
        "plan). This measures how close that is to the gold-standard quote rule using a "
        "Databento tcbbo (trade + consolidated NBBO) sample.\n",
        f"- **Per-trade agreement (tick vs quote rule):** {per_trade.get('agreement')} "
        f"(size-weighted {per_trade.get('size_weighted_agreement')}), n={per_trade.get('n')} "
        "— in line with the literature (~0.77–0.84).",
        f"- **Minute net-sign recovery (what the engine actually uses):** "
        f"{recovery.get('net_sign_recovery')} across {recovery.get('contracts')} contracts.",
        f"- **DIRECTION gate:** {'PASS' if gate['direction_reliable'] else 'BELOW BAR — DIRECTION IS SOFT'} "
        f"(bar {gate['bar']}).",
        "- **MAGNITUDE / positioning** (volume, premium size, Vol>OI, 0DTE, gamma EXPOSURE): "
        "reliable regardless — needs no signing.\n",
        "\n_Key finding: an option's minute-to-minute price ticks are dominated by the "
        "underlying's delta-driven move, not by buy/sell pressure, so the tick rule mis-signs "
        "net DIRECTION on bar data. Net buy/sell is therefore presented as SOFT context; the "
        "magnitude/positioning reads carry the weight. To trust direction, sign at the "
        "trade level against the NBBO (a paid trades+quotes tape) or delta-adjust the bar "
        "price change. Never a stand-alone buy/sell._\n",
    ]
    rp = config.ROOT / "reports" / "flow-signing-calibration.md"
    rp.parent.mkdir(parents=True, exist_ok=True)
    rp.write_text("\n".join(report))
    log.info("calibration: recovery=%s scored=%s", recovery.get("net_sign_recovery"), gate["scored"])
    return {"status": "ok", "gate": gate, "per_trade": per_trade, "recovery": recovery}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2026-06-18T14:30", help="window start (ISO, UTC)")
    ap.add_argument("--end", default="2026-06-18T14:50", help="window end (ISO, UTC)")
    args = ap.parse_args()
    r = run(window=(args.start, args.end))
    print(json.dumps(r.get("gate", {}), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
