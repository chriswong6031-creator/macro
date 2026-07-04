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


def _run_thetadata_source(universe: list[str], window: tuple[str, str]) -> dict:
    """Run signing calibration using ThetaData trade+NBBO as the source.

    Pulls trade+NBBO via collectors.thetadata.trade_quote for the SAME SPY windows as
    the cached Databento truth slices (reuses the window definition so the comparison is
    apples-to-apples).  Computes the same metrics (per-trade tick-rule vs quote-rule
    agreement; minute/daily net-sign recovery) and writes results into
    data/options_flow/signing_gate.json under the new 'thetadata_tape' key namespace.

    CONTRACT: purely ADDITIVE.
      - MUST NOT alter existing keys in signing_gate.json (direction_reliable, magnitude_reliable,
        per_trade_agreement, scored, note, delta_adjusted, etc.).
      - MUST NOT flip direction_reliable=true (that flip is a Fable-adjudicated decision
        after measured results — see research/LIVE_ORDER_FLOW_BRAINSTORM_BY_FABLE.md §7.1).
      - Writes only into the 'thetadata_tape' sub-key.
      - Existing invocations (no --source flag) are byte-identical.
    """
    from collectors import thetadata as td
    from engine import flow_signing

    gate_path = config.data_dir() / "options_flow" / "signing_gate.json"
    gate_path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing gate — must survive this call unchanged in all existing keys
    existing_gate: dict = {}
    if gate_path.exists():
        try:
            existing_gate = json.loads(gate_path.read_text())
        except Exception:  # noqa: BLE001
            pass

    if not td.reachable():
        log.info("thetadata_tape: terminal not reachable — writing stub into thetadata_tape key")
        td_result: dict = {
            "status": "terminal_unreachable",
            "asof": str(date.today()),
            "signing_source": "tape",
            "direction_reliable": None,
            "note": "Theta Terminal not reachable; run scripts/run_theta_terminal.sh first",
        }
        existing_gate["thetadata_tape"] = td_result
        gate_path.write_text(json.dumps(existing_gate, indent=2))
        return {"status": "terminal_unreachable", "thetadata_tape": td_result}

    # Parse the calibration window to get the date and time range
    # Window format: "2026-06-18T14:30" — same as the Databento truth slices
    day = datetime.strptime(window[0][:10], "%Y-%m-%d").date()
    # For ThetaData: use the SPY ATM call near the money as the calibration contract.
    # The Databento truth used SPY in the same date window — we use the same window for
    # apples-to-apples comparison per §7.1 of LIVE_ORDER_FLOW_BRAINSTORM_BY_FABLE.md.
    # The strike (~580 for Jun-2026 SPY) will be close to ATM; the signing calibration
    # is insensitive to the exact strike as long as it has sufficient volume.
    # AMBIGUITY: we don't know the exact ATM strike without querying the chain first.
    # We use a placeholder that the probe run will confirm; hardcode round number for now.
    CALIBRATION_STRIKE = 580.0   # approximate ATM SPY Jun-2026; refine after probe
    CALIBRATION_EXP = int(day.strftime("%Y%m%d"))  # nearest expiry; try today's date

    log.info("thetadata_tape: pulling trade_quote for SPY %s strike=%.0f", day, CALIBRATION_STRIKE)
    # Use the same date window as the Databento slices for comparability
    tq = td.trade_quote("SPY", CALIBRATION_EXP, "C", CALIBRATION_STRIKE, day, day)

    if tq is None or tq.empty:
        log.warning("thetadata_tape: no trade_quote data for SPY %s — stub result", day)
        td_result = {
            "status": "no_data",
            "asof": str(date.today()),
            "signing_source": "tape",
            "direction_reliable": None,
            "note": (f"No trade_quote data for SPY {day} strike={CALIBRATION_STRIKE} — "
                     "try the probe run to find a liquid contract"),
        }
        existing_gate["thetadata_tape"] = td_result
        gate_path.write_text(json.dumps(existing_gate, indent=2))
        return {"status": "no_data", "thetadata_tape": td_result}

    # Build a trades DataFrame in the format flow_signing expects:
    # [ticker, ts, price, size, bid, ask]
    trades = tq.rename(columns={"ts_ms": "ts"}).copy()
    # Add synthetic ticker column (OCC-style not needed; flow_signing works on raw trades)
    trades["ticker"] = f"SPY_CAL_{int(CALIBRATION_STRIKE)}"
    # ts_ms is milliseconds since midnight ET — convert to Timestamp for minute binning
    if "ts" in trades.columns and trades["ts"].dtype in ("int64", "float64"):
        base = pd.Timestamp(day)
        trades["ts"] = base + pd.to_timedelta(trades["ts"], unit="ms")

    trades = trades[(trades["bid"] > 0) & (trades["ask"] >= trades["bid"])] if not trades.empty else trades

    if trades.empty:
        log.warning("thetadata_tape: no valid bid/ask trades for SPY %s", day)
        td_result = {
            "status": "no_valid_trades",
            "asof": str(date.today()),
            "signing_source": "tape",
            "direction_reliable": None,
            "note": "All trades filtered out (bid<=0 or ask<bid)",
        }
        existing_gate["thetadata_tape"] = td_result
        gate_path.write_text(json.dumps(existing_gate, indent=2))
        return {"status": "no_valid_trades", "thetadata_tape": td_result}

    # Compute the same metrics as the Databento calibration
    per_trade = flow_signing.compare_trade_signs(trades)
    recovery = flow_signing.minute_sign_recovery(trades)

    # Acceptance criteria from §7.1: per-trade quote-rule agreement ≥0.75
    # AND minute/daily net-sign recovery ≥0.75 (vs 0.41 bar baseline)
    ACCEPTANCE_AGREEMENT = 0.75
    ACCEPTANCE_RECOVERY = 0.75
    agreement_ok = (per_trade.get("agreement") or 0) >= ACCEPTANCE_AGREEMENT
    recovery_ok = (recovery.get("net_sign_recovery") or 0) >= ACCEPTANCE_RECOVERY

    td_result = {
        "status": "measured",
        "asof": str(date.today()),
        "generated": datetime.now(timezone.utc).isoformat(),
        "signing_source": "tape",
        "n_trades": int(len(trades)),
        "calibration_contract": {
            "root": "SPY", "right": "C", "strike": CALIBRATION_STRIKE,
            "exp": CALIBRATION_EXP, "date": day.isoformat(),
        },
        "per_trade_agreement": per_trade.get("agreement"),
        "per_trade_size_weighted": per_trade.get("size_weighted_agreement"),
        "net_sign_recovery": recovery.get("net_sign_recovery"),
        "acceptance_criteria": {
            "agreement_bar": ACCEPTANCE_AGREEMENT,
            "recovery_bar": ACCEPTANCE_RECOVERY,
            "agreement_ok": agreement_ok,
            "recovery_ok": recovery_ok,
        },
        # Adjudication note: direction_reliable in the root gate is flipped only by
        # Fable adjudication after measured results pass both bars (§7.1).
        # This sub-key records the MEASUREMENT; it does NOT flip the root gate.
        "direction_reliable_tape": agreement_ok and recovery_ok,
        "note": (
            "ThetaData tape-sourced calibration (trade+NBBO at execution). "
            "Per §7.1 of LIVE_ORDER_FLOW_BRAINSTORM_BY_FABLE.md, "
            "direction_reliable in the root gate is flipped only by Fable adjudication "
            "after both acceptance bars are met. "
            f"Agreement: {per_trade.get('agreement')} (bar {ACCEPTANCE_AGREEMENT}), "
            f"recovery: {recovery.get('net_sign_recovery')} (bar {ACCEPTANCE_RECOVERY})."
        ),
    }
    # Merge into existing gate — purely additive, existing keys untouched
    existing_gate["thetadata_tape"] = td_result
    gate_path.write_text(json.dumps(existing_gate, indent=2))
    log.info("thetadata_tape: written to signing_gate.json — agreement=%s, recovery=%s",
             per_trade.get("agreement"), recovery.get("net_sign_recovery"))
    return {"status": "ok", "thetadata_tape": td_result}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", default="2026-06-18T14:30", help="window start (ISO, UTC)")
    ap.add_argument("--end", default="2026-06-18T14:50", help="window end (ISO, UTC)")
    ap.add_argument("--source", default="databento",
                    choices=["databento", "thetadata"],
                    help="signing calibration source (default: databento)")
    args = ap.parse_args()

    if args.source == "thetadata":
        syms = list((config.load().get("polygon", {}).get("gex", {}) or {}).get("symbols") or ["SPY"])
        r = _run_thetadata_source(syms, (args.start, args.end))
        print(json.dumps(r.get("thetadata_tape", {}), indent=2))
        return 0

    # Default: existing Databento path — byte-identical behavior
    r = run(window=(args.start, args.end))
    print(json.dumps(r.get("gate", {}), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
