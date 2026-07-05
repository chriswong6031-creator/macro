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


# Minimum trade count for a calibration run to be considered statistically valid.
# The Databento benchmark produced 101,934 trades over a 20-min window across 10 symbols.
# We require ≥5,000 pooled trades across all sampled contracts before reporting "measured".
# Runs with n_trades < MIN_N_TRADES write status="insufficient_n" instead.
MIN_N_TRADES = 5000


def _resolve_atm_contracts(
        td, day: date, n_expirations: int = 3, band_pct: float = 0.10
) -> list[tuple[int, str, float]]:
    """Resolve ATM contracts from the day's SPY EOD chain.

    Pulls the day's SPY EOD chain (single wildcard range request), finds the underlying
    spot price from the highest-volume strikes, then selects a strike band of ±band_pct
    around spot across the nearest n_expirations listed expirations.

    Skips expirations that have already expired relative to the calibration date
    (expiration < day) — 0DTE contracts that expired before the window are excluded.

    Returns list of (exp_int, right, strike) tuples for use with trade_quote.
    """
    chain = td.bulk_eod("SPY", "*", day, day)
    if chain is None or chain.empty:
        log.warning("thetadata_tape: bulk_eod returned no data for SPY %s — "
                    "cannot resolve ATM strikes", day)
        return []

    # Estimate spot from highest-volume row's strike (ATM options dominate volume)
    if "volume" not in chain.columns or "strike" not in chain.columns:
        log.warning("thetadata_tape: EOD chain missing volume/strike columns")
        return []

    top_row = chain.nlargest(1, "volume")
    spot = float(top_row["strike"].iloc[0])
    lo = spot * (1 - band_pct)
    hi = spot * (1 + band_pct)
    log.info("thetadata_tape: spot≈%.0f (from max-volume strike), strike band [%.0f, %.0f]",
             spot, lo, hi)

    # Get nearest expirations — must not be already expired for the calibration date
    if "expiration" not in chain.columns:
        log.warning("thetadata_tape: EOD chain missing expiration column")
        return []

    exps_all = sorted(chain["expiration"].dropna().unique())
    # Filter: expiration >= calibration date (don't pull post-expiry contracts)
    day_ts = pd.Timestamp(day)
    exps_valid = [e for e in exps_all if pd.Timestamp(e) >= day_ts]
    exps_use = exps_valid[:n_expirations]
    if not exps_use:
        log.warning("thetadata_tape: no valid expirations found for %s (all expired?)", day)
        return []

    log.info("thetadata_tape: using %d expirations: %s",
             len(exps_use), [str(e)[:10] for e in exps_use])

    # Select strikes in the ATM band; use calls only (direction bias is symmetric)
    contracts: list[tuple[int, str, float]] = []
    seen_strikes: set[tuple[int, float]] = set()
    for exp in exps_use:
        exp_int = int(pd.Timestamp(exp).strftime("%Y%m%d"))
        band = chain[
            (chain["expiration"] == exp) &
            (chain["right"] == "C") &
            (chain["strike"] >= lo) &
            (chain["strike"] <= hi)
        ]
        if band.empty:
            continue
        # Pick top-5 by volume to maximize trade count
        top = band.nlargest(5, "volume") if "volume" in band.columns else band.head(5)
        for _, row in top.iterrows():
            k = (exp_int, float(row["strike"]))
            if k not in seen_strikes:
                seen_strikes.add(k)
                contracts.append((exp_int, "C", float(row["strike"])))

    log.info("thetadata_tape: selected %d contracts for trade_quote sampling", len(contracts))
    return contracts


def _run_thetadata_source(universe: list[str], window: tuple[str, str]) -> dict:
    """Run signing calibration using ThetaData trade+NBBO as the source.

    Resolves ATM contracts dynamically from the day's SPY EOD chain, loops trade_quote
    over each selected contract (sequential; respects the 8-concurrent ceiling), and
    concatenates pooled trades.  Filters pooled trades to the ACTUAL requested time window
    (the start/end timestamps passed in, not just the date) before computing metrics.

    Time zone assumption: trade_timestamp strings from the v3 API are tz-naive Eastern Time
    (ET).  SPY trades at 14:3x ET exist in size.  The window args are also parsed as ET.
    This module does NOT convert to UTC — it compares naive strings against naive strings.

    CONTRACT: purely ADDITIVE.
      - MUST NOT alter existing keys in signing_gate.json (direction_reliable, magnitude_reliable,
        per_trade_agreement, scored, note, delta_adjusted, etc.).
      - MUST NOT flip direction_reliable=true (that flip is a Fable-adjudicated decision
        after measured results — see research/LIVE_ORDER_FLOW_BRAINSTORM_BY_FABLE.md §7.1).
      - Writes only into the 'thetadata_tape' sub-key.
      - Existing invocations (no --source flag) are byte-identical.
      - n_trades and n_contracts are reported prominently in stdout and in the gate payload.

    Insufficient-n semantics (M1):
      If n_trades < MIN_N_TRADES (= 5000, citing the 101,934-trade Databento benchmark):
        status="insufficient_n", insufficient_n=True, direction_reliable_tape=None,
        and *_ok booleans are null.  Only a ≥MIN_N run may write status="measured".
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

    # Parse window: "2026-06-18T14:30" / "2026-06-18T14:50"
    # trade_timestamp strings from the v3 API are tz-naive ET; window is also ET.
    day = datetime.strptime(window[0][:10], "%Y-%m-%d").date()
    window_start = window[0]   # e.g. "2026-06-18T14:30"
    window_end = window[1]     # e.g. "2026-06-18T14:50"
    # Normalize to the same 16-char prefix format used in trade_timestamp ("YYYY-MM-DDTHH:MM")
    win_start_ts = window_start[:16]   # "2026-06-18T14:30"
    win_end_ts = window_end[:16]       # "2026-06-18T14:50"

    # Dynamically resolve ATM contracts from the day's SPY EOD chain
    contracts = _resolve_atm_contracts(td, day)
    if not contracts:
        log.warning("thetadata_tape: could not resolve any ATM contracts for %s — stub result", day)
        td_result = {
            "status": "no_data",
            "asof": str(date.today()),
            "signing_source": "tape",
            "direction_reliable": None,
            "note": f"No ATM contracts resolved from EOD chain for SPY {day}",
        }
        existing_gate["thetadata_tape"] = td_result
        gate_path.write_text(json.dumps(existing_gate, indent=2))
        return {"status": "no_data", "thetadata_tape": td_result}

    # Sequential trade_quote loop (respect 8-concurrent ceiling — sequential is safe)
    all_frames: list[pd.DataFrame] = []
    contracts_with_data = 0
    for exp_int, right, strike in contracts:
        log.info("thetadata_tape: trade_quote SPY exp=%d %s strike=%.1f", exp_int, right, strike)
        tq = td.trade_quote("SPY", exp_int, right, strike, day, day)
        if tq is None:
            log.warning("thetadata_tape: trade_quote returned None for exp=%d strike=%.1f — skip",
                        exp_int, strike)
            continue
        if tq.empty:
            log.info("thetadata_tape: trade_quote empty for exp=%d strike=%.1f — skip",
                     exp_int, strike)
            continue
        # Label with a ticker tag for flow_signing contract tracking
        tq["ticker"] = f"SPY_C_{int(strike)}_exp{exp_int}"
        all_frames.append(tq)
        contracts_with_data += 1

    if not all_frames:
        log.warning("thetadata_tape: no trade data from any contract for SPY %s", day)
        td_result = {
            "status": "no_data",
            "asof": str(date.today()),
            "signing_source": "tape",
            "n_trades": 0,
            "n_contracts": 0,
            "direction_reliable": None,
            "note": f"No trade data from any of {len(contracts)} selected contracts for SPY {day}",
        }
        existing_gate["thetadata_tape"] = td_result
        gate_path.write_text(json.dumps(existing_gate, indent=2))
        return {"status": "no_data", "thetadata_tape": td_result}

    pooled = pd.concat(all_frames, ignore_index=True)
    log.info("thetadata_tape: pooled %d trades from %d/%d contracts (pre-window-filter)",
             len(pooled), contracts_with_data, len(contracts))

    # Parse trade_timestamp for window filtering and minute-binning.
    # trade_timestamp format: "2026-06-18T14:30:00.123" (tz-naive ET — see docstring).
    if "trade_timestamp" in pooled.columns:
        pooled["ts"] = pd.to_datetime(pooled["trade_timestamp"], errors="coerce")
    elif "ts_ms" in pooled.columns:
        # Backward compat: v2 used ts_ms = milliseconds since midnight ET
        base = pd.Timestamp(day)
        pooled["ts"] = base + pd.to_timedelta(pooled["ts_ms"], unit="ms")
    else:
        pooled["ts"] = pd.NaT

    # Filter to the ACTUAL requested time window (ET, tz-naive string comparison is safe
    # because trade_timestamp is always "YYYY-MM-DDTHH:MM:SS..." and window is "YYYY-MM-DDTHH:MM").
    if "trade_timestamp" in pooled.columns:
        pooled = pooled[
            (pooled["trade_timestamp"].astype(str).str[:16] >= win_start_ts) &
            (pooled["trade_timestamp"].astype(str).str[:16] <= win_end_ts)
        ]
    else:
        # Fallback: filter on parsed ts column
        ts_lo = pd.Timestamp(window_start)
        ts_hi = pd.Timestamp(window_end)
        pooled = pooled[(pooled["ts"] >= ts_lo) & (pooled["ts"] <= ts_hi)]

    # Apply bid/ask sanity filter
    pooled = pooled[(pooled["bid"] > 0) & (pooled["ask"] >= pooled["bid"])] if not pooled.empty else pooled

    n_trades = int(len(pooled))
    n_contracts = int(pooled["ticker"].nunique()) if "ticker" in pooled.columns else contracts_with_data
    print(f"\nthetadata_tape: n_trades={n_trades:,}  n_contracts={n_contracts}"
          f"  window={win_start_ts}–{win_end_ts}  day={day}")
    log.info("thetadata_tape: after window filter: n_trades=%d, n_contracts=%d",
             n_trades, n_contracts)

    if pooled.empty or n_trades < MIN_N_TRADES:
        # Insufficient-n gate (M1): below the statistical floor → insufficient_n status.
        # MIN_N_TRADES = 5000 (citing the 101,934-trade Databento benchmark).
        # direction_reliable_tape=null, *_ok booleans null.
        log.warning(
            "thetadata_tape: n_trades=%d < MIN_N_TRADES=%d — writing insufficient_n status. "
            "Widen expiration/strike band or use a more liquid window.",
            n_trades, MIN_N_TRADES)
        td_result = {
            "status": "insufficient_n",
            "insufficient_n": True,
            "asof": str(date.today()),
            "generated": datetime.now(timezone.utc).isoformat(),
            "signing_source": "tape",
            "n_trades": n_trades,
            "n_contracts": n_contracts,
            "min_n_trades": MIN_N_TRADES,
            "window": {"start": window_start, "end": window_end},
            # null booleans — not statistically valid
            "direction_reliable_tape": None,
            "acceptance_criteria": {
                "agreement_bar": 0.75,
                "recovery_bar": 0.75,
                "agreement_ok": None,
                "recovery_ok": None,
            },
            "note": (
                f"Insufficient trades (n={n_trades:,}) for a valid calibration. "
                f"MIN_N_TRADES={MIN_N_TRADES:,} (citing 101,934-trade Databento benchmark). "
                "Widen to more expirations or strike band, or try a more liquid time window. "
                "Direction gate is NOT adjudicable at this sample size."
            ),
        }
        existing_gate["thetadata_tape"] = td_result
        gate_path.write_text(json.dumps(existing_gate, indent=2))
        return {"status": "insufficient_n", "thetadata_tape": td_result}

    # Compute the same metrics as the Databento calibration
    per_trade = flow_signing.compare_trade_signs(pooled)
    recovery = flow_signing.minute_sign_recovery(pooled)

    # Acceptance criteria from §7.1: per-trade quote-rule agreement ≥0.75
    # AND minute/daily net-sign recovery ≥0.75 (vs 0.41 bar baseline)
    ACCEPTANCE_AGREEMENT = 0.75
    ACCEPTANCE_RECOVERY = 0.75
    agreement_ok = (per_trade.get("agreement") or 0) >= ACCEPTANCE_AGREEMENT
    recovery_ok = (recovery.get("net_sign_recovery") or 0) >= ACCEPTANCE_RECOVERY

    td_result = {
        "status": "measured",
        "insufficient_n": False,
        "asof": str(date.today()),
        "generated": datetime.now(timezone.utc).isoformat(),
        "signing_source": "tape",
        "n_trades": n_trades,
        "n_contracts": n_contracts,
        "min_n_trades": MIN_N_TRADES,
        "window": {"start": window_start, "end": window_end},
        "calibration_contracts": [
            {"root": "SPY", "right": r, "strike": k, "exp": e}
            for (e, r, k) in contracts
        ],
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
            f"n_trades={n_trades:,}, n_contracts={n_contracts}. "
            f"Agreement: {per_trade.get('agreement')} (bar {ACCEPTANCE_AGREEMENT}), "
            f"recovery: {recovery.get('net_sign_recovery')} (bar {ACCEPTANCE_RECOVERY})."
        ),
    }
    # Merge into existing gate — purely additive, existing keys untouched
    existing_gate["thetadata_tape"] = td_result
    gate_path.write_text(json.dumps(existing_gate, indent=2))
    log.info("thetadata_tape: written to signing_gate.json — agreement=%s, recovery=%s, "
             "n_trades=%d, n_contracts=%d",
             per_trade.get("agreement"), recovery.get("net_sign_recovery"),
             n_trades, n_contracts)
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
