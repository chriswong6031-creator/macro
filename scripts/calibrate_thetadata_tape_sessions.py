"""scripts/calibrate_thetadata_tape_sessions.py — multi-session ThetaData tape calibration harness.

PURPOSE
-------
Accumulate calibration evidence across multiple historical sessions (date × time-window ×
roots × contract set) to measure whether ThetaData trade+NBBO signing is stable across
market conditions. This is the continuous-validation follow-up registered in
research/THETADATA_PROBE.md §4.6 and governed by RUL-F3.12.

A "session" = one measured window: a date, a 20-minute time range, a set of roots, a
set of contracts (mixed moneyness, both calls and puts). Each session appends one record
to data/options_flow/tape_signing_sessions.jsonl (append-only; never rewritten).

After appending, the script updates ONLY the thetadata_tape sub-key of
data/options_flow/signing_gate.json with aggregate stats:
  sessions_n, sessions_passed, conditions_covered, last_session, production_ready,
  suspend_reason (if any session fails).

METHODOLOGY
-----------
Each trade is classified against the prevailing NBBO using the Lee-Ready quote rule
(engine.flow_signing.quote_rule_sign). Agreement = fraction of trades where the quote
rule and tick rule agree. Net-sign recovery = fraction of contracts where the
minute-aggregated tick-rule net sign matches the quote-rule net sign.

For ThetaData tape sessions: the NBBO IS available in trade_quote records. The quote rule
is thus fully applicable — this is the same method used in the ratified #1292 session
(which also used ThetaData's own NBBO via the identical quote-rule-vs-tick-rule code path).
Both the #1292 session and all sessions measured here are 'quote_rule_self_consistency'
measurements: no external third-party oracle is available, so we cannot cross-validate
between providers. The metric is labelled 'quote_rule_self_consistency' in every record to
document this plainly. The '0.777 Databento truth' in THETADATA_PROBE.md §4.4 is the
separate bar-data baseline (root gate per_trade_agreement=0.7774 — a different instrument
from the tape calibration). The real driver of the 0.88→0.67–0.72 drop between the
ratified session and the multi-session harness is the expansion to puts + multiple roots +
additional dates (correctly documented in §5 of the calibration doc).

HOUSE LAW COMPLIANCE (RUL-F3.12)
---------------------------------
- Sessions log: append-only JSONL; never rewrite past records.
- Gate updater: writes ONLY thetadata_tape sub-key; root direction_reliable stays false
  for bar sources PERMANENTLY.
- Suspend: ANY session with per_trade_agreement < 0.75 sets direction_reliable_tape=false
  with suspend_reason until manual review.
- production_ready=true ONLY when >=5 sessions, at least one high-VIX and one calm,
  multiple roots (>=2), multiple expiries (>=2 distinct expiry dates across sessions),
  multiple moneyness buckets (>=2 distinct buckets across sessions), all passing.
  (Per RUL-F3.12: "spanning high-VIX and calm, multiple roots/expiries/moneyness.")

USAGE
-----
  # Dry-run (no network, synthetic fixture data)
  python -m scripts.calibrate_thetadata_tape_sessions --dry-run

  # Single session from ThetaData history (requires terminal running on :25503)
  python -m scripts.calibrate_thetadata_tape_sessions \\
      --date 2025-04-07 --start 14:30 --end 14:50 \\
      --roots SPY,QQQ,NVDA

  # Run a pre-defined multi-session plan (all sessions in sequence)
  python -m scripts.calibrate_thetadata_tape_sessions --run-plan

  # Show current session log summary (no new session)
  python -m scripts.calibrate_thetadata_tape_sessions --summary
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

# Repo root on sys.path (same pattern as other scripts)
_REPO = Path(__file__).parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from engine import flow_signing
from lib import config

log = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────────────────────────
# Constants (house-law-governed)
# ────────────────────────────────────────────────────────────────────────────

AGREEMENT_BAR = 0.75       # per-trade quote-rule agreement threshold
RECOVERY_BAR = 0.75        # net-sign recovery threshold
MIN_N_TRADES = 5_000       # minimum trades for a session to be non-insufficient_n
VIX_HIGH_THRESHOLD = 20.0  # >= this → high-VIX session
SESSIONS_NEEDED = 5        # production_ready bar: session count
ROOTS_NEEDED = 2           # production_ready bar: distinct roots

# Path constants
SESSIONS_JSONL = "options_flow/tape_signing_sessions.jsonl"
SIGNING_GATE = "options_flow/signing_gate.json"

# Window-stall law: ThetaTerminal v3 can stall; use short connect timeout
CONNECT_TIMEOUT = 5  # seconds — do NOT hang; treat stall as unreachable

# ────────────────────────────────────────────────────────────────────────────
# VIX regime lookup
# ────────────────────────────────────────────────────────────────────────────

def _vix_for_date(target: date) -> Optional[float]:
    """Return the on-disk VIX closing level for target date.

    Reads data/fred/VIXCLS.parquet if available. Returns None if missing.
    Does NOT fall back to network — avoids dependency on live internet during calibration.
    """
    try:
        vix_path = config.data_dir() / "fred" / "VIXCLS.parquet"
        if not vix_path.exists():
            log.info("vix_for_date: VIXCLS.parquet not found — vix_close will be null")
            return None
        df = pd.read_parquet(vix_path)
        col = "vix_close" if "vix_close" in df.columns else df.columns[0]
        # Index is datetime; convert target to Timestamp
        ts = pd.Timestamp(target)
        if ts in df.index:
            val = float(df.loc[ts, col])
            return round(val, 2)
        # Try by date string (index may be date only)
        date_str = str(target)
        if date_str in df.index.astype(str):
            val = float(df[df.index.astype(str) == date_str][col].iloc[0])
            return round(val, 2)
        log.info("vix_for_date: %s not in VIXCLS index — vix_close will be null", target)
        return None
    except Exception as exc:  # noqa: BLE001
        log.info("vix_for_date: error reading VIXCLS.parquet — %s", exc)
        return None


def _vix_regime(vix_close: Optional[float]) -> str:
    """Classify VIX level as 'high' or 'calm'. 'unknown' if vix_close is None."""
    if vix_close is None:
        return "unknown"
    return "high" if vix_close >= VIX_HIGH_THRESHOLD else "calm"


# ────────────────────────────────────────────────────────────────────────────
# ATM contract resolution (multi-root, both rights)
# ────────────────────────────────────────────────────────────────────────────

def _resolve_contracts_for_root(
    td,
    root: str,
    day: date,
    n_expirations: int = 3,
    band_pct: float = 0.10,
    n_per_expiry: int = 3,
    include_puts: bool = True,
) -> tuple[list[tuple[int, str, float]], float]:
    """Resolve ATM + near-ATM contracts for a single root.

    Returns (contracts, spot) where contracts is a list of (exp_int, right, strike) tuples.
    spot is the estimated underlying price (0.0 if unavailable).
    Includes both calls and puts when include_puts=True.
    """
    chain = td.bulk_eod(root, "*", day, day)
    if chain is None or chain.empty:
        log.warning("contracts: bulk_eod returned no data for %s %s", root, day)
        return [], 0.0

    if "volume" not in chain.columns or "strike" not in chain.columns:
        log.warning("contracts: EOD chain missing volume/strike columns for %s", root)
        return [], 0.0

    # Spot estimate from highest-volume call strike
    calls_only = chain[chain["right"] == "C"] if "right" in chain.columns else chain
    if calls_only.empty:
        calls_only = chain
    top_row = calls_only.nlargest(1, "volume")
    spot = float(top_row["strike"].iloc[0])
    lo = spot * (1 - band_pct)
    hi = spot * (1 + band_pct)
    log.info("contracts: %s spot≈%.2f band [%.2f, %.2f]", root, spot, lo, hi)

    if "expiration" not in chain.columns:
        log.warning("contracts: EOD chain missing expiration column for %s", root)
        return [], spot

    exps_all = sorted(chain["expiration"].dropna().unique())
    day_ts = pd.Timestamp(day)
    exps_valid = [e for e in exps_all if pd.Timestamp(e) >= day_ts]
    exps_use = exps_valid[:n_expirations]
    if not exps_use:
        log.warning("contracts: no valid expirations for %s %s", root, day)
        return [], spot

    rights = ["C", "P"] if include_puts else ["C"]
    contracts: list[tuple[int, str, float]] = []
    seen: set[tuple[int, str, float]] = set()

    for exp in exps_use:
        exp_int = int(pd.Timestamp(exp).strftime("%Y%m%d"))
        for right in rights:
            band = chain[
                (chain["expiration"] == exp)
                & (chain["right"] == right)
                & (chain["strike"] >= lo)
                & (chain["strike"] <= hi)
            ] if "right" in chain.columns else pd.DataFrame()

            if band.empty:
                # Fallback: nearest n strikes
                band = chain[
                    (chain["expiration"] == exp)
                    & (chain["strike"] >= lo)
                    & (chain["strike"] <= hi)
                ]

            if band.empty:
                continue

            top = band.nlargest(n_per_expiry, "volume") if "volume" in band.columns else band.head(n_per_expiry)
            for _, row in top.iterrows():
                key = (exp_int, right, float(row["strike"]))
                if key not in seen:
                    seen.add(key)
                    contracts.append(key)

    log.info("contracts: %s — selected %d contracts across %d expirations",
             root, len(contracts), len(exps_use))
    return contracts, spot


def _moneyness_bucket(strike: float, spot: float) -> str:
    """Classify moneyness: ATM if within 2%, OTM/ITM by side."""
    if spot == 0:
        return "unknown"
    ratio = strike / spot
    if 0.98 <= ratio <= 1.02:
        return "ATM"
    elif ratio > 1.02:
        return "OTM-call"  # strike above spot = OTM for calls, ITM for puts
    else:
        return "OTM-put"   # strike below spot = ITM for calls, OTM for puts


# ────────────────────────────────────────────────────────────────────────────
# Session runner
# ────────────────────────────────────────────────────────────────────────────

def _run_session_live(
    roots: list[str],
    day: date,
    window_start: str,   # "HH:MM" ET
    window_end: str,     # "HH:MM" ET
) -> dict:
    """Pull ThetaData tape for one session; compute agreement and recovery.

    Returns a session dict (does NOT write to disk; caller does that).
    """
    from collectors import thetadata as td

    # Resolve contracts for each root
    all_contracts: dict[str, list[tuple[int, str, float]]] = {}
    spot_by_root: dict[str, float] = {}

    for root in roots:
        contracts, spot = _resolve_contracts_for_root(
            td, root, day,
            n_expirations=3,
            band_pct=0.10,
            n_per_expiry=3,
            include_puts=True,
        )
        all_contracts[root] = contracts
        spot_by_root[root] = spot

    # Collect trades for each contract
    pooled_dfs: list[pd.DataFrame] = []
    contracts_hit = 0
    contracts_tried = 0

    for root, ctrs in all_contracts.items():
        for exp_int, right, strike in ctrs:
            contracts_tried += 1
            log.info("session: trade_quote %s exp=%d %s strike=%.1f", root, exp_int, right, strike)
            tq = td.trade_quote(root, exp_int, right, strike, day, day)
            if tq is None:
                log.warning("session: trade_quote returned None for %s exp=%d strike=%.1f",
                            root, exp_int, strike)
                continue
            if tq.empty:
                log.info("session: trade_quote empty for %s exp=%d strike=%.1f",
                         root, exp_int, strike)
                continue
            contracts_hit += 1
            # Tag with root + right + strike for grouping
            tq = tq.copy()
            tq["ticker"] = f"{root}_{right}_{int(strike)}"
            # Window filter: keep only trades within the ET time window
            if "trade_timestamp" in tq.columns:
                tq["ts"] = pd.to_datetime(tq["trade_timestamp"], errors="coerce")
                # Parse window bounds
                win_start_ts = pd.Timestamp(f"{day}T{window_start}:00", tz="America/New_York")
                win_end_ts = pd.Timestamp(f"{day}T{window_end}:00", tz="America/New_York")
                # Handle tz-naive timestamps from ThetaData (assume ET)
                if tq["ts"].dt.tz is None:
                    tq = tq[
                        (tq["ts"] >= win_start_ts.replace(tzinfo=None))
                        & (tq["ts"] <= win_end_ts.replace(tzinfo=None))
                    ]
                else:
                    tq = tq[(tq["ts"] >= win_start_ts) & (tq["ts"] <= win_end_ts)]
            else:
                tq["ts"] = pd.Timestamp(f"{day}T{window_start}:00")

            if not tq.empty:
                pooled_dfs.append(tq)

    if not pooled_dfs:
        log.warning("session: no trade data from any contract on %s roots=%s", day, roots)
        return {
            "status": "no_data",
            "error": "no trades from any contract after window filter",
        }

    pooled = pd.concat(pooled_dfs, ignore_index=True)
    n_trades = len(pooled)
    log.info("session: pooled %d trades from %d/%d contracts", n_trades, contracts_hit, contracts_tried)

    if n_trades < MIN_N_TRADES:
        log.warning("session: n_trades=%d < MIN_N_TRADES=%d — insufficient_n", n_trades, MIN_N_TRADES)
        return {
            "status": "insufficient_n",
            "n_trades": n_trades,
            "n_contracts": contracts_hit,
            "contracts_tried": contracts_tried,
            "error": f"n_trades={n_trades} < MIN_N_TRADES={MIN_N_TRADES}",
        }

    # Compute metrics using engine.flow_signing
    per_trade = flow_signing.compare_trade_signs(pooled)
    recovery = flow_signing.minute_sign_recovery(pooled)

    # Moneyness coverage
    moneyness_buckets: set[str] = set()
    for root, ctrs in all_contracts.items():
        spot = spot_by_root.get(root, 0.0)
        for _, _, strike in ctrs:
            moneyness_buckets.add(_moneyness_bucket(strike, spot))

    # Expiry coverage
    expiries_seen: set[str] = set()
    for ctrs in all_contracts.values():
        for exp_int, _, _ in ctrs:
            expiries_seen.add(str(exp_int))

    return {
        "status": "ok",
        "n_trades": n_trades,
        "n_contracts": contracts_hit,
        "contracts_tried": contracts_tried,
        "per_trade_agreement": per_trade.get("agreement"),
        "per_trade_size_weighted": per_trade.get("size_weighted_agreement"),
        "net_sign_recovery": recovery.get("net_sign_recovery"),
        "moneyness_buckets": sorted(moneyness_buckets),
        "expiries_covered": sorted(expiries_seen),
        "roots_measured": roots,
    }


# ────────────────────────────────────────────────────────────────────────────
# Dry-run fixture
# ────────────────────────────────────────────────────────────────────────────

def _make_fixture_trades(
    n: int = 8000,
    agreement_target: float = 0.88,
    recovery_target: float = 0.82,
    seed: int = 42,
) -> pd.DataFrame:
    """Synthetic trade fixture for --dry-run and unit tests.

    Constructs a DataFrame matching the schema expected by flow_signing:
    [ticker, price, bid, ask, size, ts].

    Agreement and recovery are approximate targets — exact values vary by seed.
    """
    import numpy as np

    rng = np.random.default_rng(seed)
    n_per = n // 3  # 3 tickers

    rows = []
    base_time = pd.Timestamp("2025-04-07T14:30:00")
    for ticker_i, ticker in enumerate(["SPY_C_550", "QQQ_C_470", "NVDA_P_100"]):
        price = 2.0 + ticker_i * 0.5  # starting price
        bid = price - 0.05
        ask = price + 0.05
        for j in range(n_per):
            ts = base_time + pd.Timedelta(seconds=j * 0.15)
            # Simulate a price path
            dp = rng.normal(0, 0.01)
            price = max(0.01, price + dp)
            # Align bid/ask with price most of the time (simulates real bid-ask)
            bid = price - abs(rng.normal(0, 0.03))
            ask = price + abs(rng.normal(0, 0.03))
            rows.append({
                "ticker": ticker,
                "price": round(price, 4),
                "bid": round(max(0.01, bid), 4),
                "ask": round(max(bid + 0.01, ask), 4),
                "size": int(rng.integers(1, 20)),
                "ts": ts,
            })

    df = pd.DataFrame(rows)
    return df


def _run_session_dry(
    roots: list[str],
    day: date,
    window_start: str,
    window_end: str,
    seed: int = 42,
) -> dict:
    """Dry-run session: compute metrics on synthetic fixture data."""
    trades = _make_fixture_trades(seed=seed)
    per_trade = flow_signing.compare_trade_signs(trades)
    recovery = flow_signing.minute_sign_recovery(trades)

    return {
        "status": "dry_run",
        "n_trades": len(trades),
        "n_contracts": 3,
        "contracts_tried": 3,
        "per_trade_agreement": per_trade.get("agreement"),
        "per_trade_size_weighted": per_trade.get("size_weighted_agreement"),
        "net_sign_recovery": recovery.get("net_sign_recovery"),
        "moneyness_buckets": ["ATM", "OTM-call"],
        "expiries_covered": ["20250407", "20250414"],
        "roots_measured": roots,
    }


# ────────────────────────────────────────────────────────────────────────────
# Session record builder
# ────────────────────────────────────────────────────────────────────────────

def _build_session_record(
    day: date,
    window_start: str,
    window_end: str,
    roots: list[str],
    run_result: dict,
) -> dict:
    """Build a flat session record for the JSONL log.

    Agreement methodology note: agreement is computed between the Lee-Ready quote rule
    (using ThetaData NBBO at execution) and the tick rule. This is the same methodology
    as the ratified #1292 session — both use ThetaData's own NBBO via the identical
    quote-rule-vs-tick-rule code path (engine.flow_signing.compare_trade_signs). No
    external third-party oracle exists for either session; the metric is labelled
    'quote_rule_self_consistency' in every record to document this plainly. This property
    is NOT new to the multi-session harness — it also applies to the ratified #1292
    session. The '0.777 Databento truth' referenced in THETADATA_PROBE.md §4.4 is the
    bar-data baseline (root gate, a different instrument), not the tape calibration oracle.
    """
    vix = _vix_for_date(day)
    regime = _vix_regime(vix)
    pt_agr = run_result.get("per_trade_agreement")
    nsr = run_result.get("net_sign_recovery")
    agreement_ok = bool(pt_agr >= AGREEMENT_BAR) if pt_agr is not None else None
    recovery_ok = bool(nsr >= RECOVERY_BAR) if nsr is not None else None
    session_pass = (agreement_ok is True) and (recovery_ok is True)

    record: dict = {
        "date": str(day),
        "window_start": f"{day}T{window_start}",
        "window_end": f"{day}T{window_end}",
        "roots": sorted(roots),
        "n_contracts": run_result.get("n_contracts", 0),
        "n_trades": run_result.get("n_trades", 0),
        "per_trade_agreement": pt_agr,
        "net_sign_recovery": nsr,
        "vix_close": vix,
        "vix_regime": regime,
        "moneyness_buckets": run_result.get("moneyness_buckets", []),
        "expiries_covered": run_result.get("expiries_covered", []),
        "agreement_ok": agreement_ok,
        "recovery_ok": recovery_ok,
        "pass": session_pass,
        "status": run_result.get("status", "unknown"),
        "agreement_bar": AGREEMENT_BAR,
        "recovery_bar": RECOVERY_BAR,
        # Methodology note: written into every record
        "agreement_method": "quote_rule_self_consistency",
        "agreement_note": (
            "Agreement between Lee-Ready quote rule (ThetaData NBBO at execution) and "
            "tick rule. No external oracle. See scripts/calibrate_thetadata_tape_sessions.py §METHODOLOGY."
        ),
        "recorded": datetime.now(timezone.utc).isoformat(),
    }
    if run_result.get("status") in ("no_data", "insufficient_n"):
        record["error"] = run_result.get("error", "")
    return record


# ────────────────────────────────────────────────────────────────────────────
# JSONL append
# ────────────────────────────────────────────────────────────────────────────

def _append_to_jsonl(record: dict, path: Optional[Path] = None) -> Path:
    """Append one session record to tape_signing_sessions.jsonl (append-only).

    Never rewrites the file. Returns the path written.
    """
    if path is None:
        path = config.data_dir() / SESSIONS_JSONL
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    log.info("sessions_jsonl: appended to %s", path)
    return path


# ────────────────────────────────────────────────────────────────────────────
# Gate updater — writes ONLY thetadata_tape sub-key
# ────────────────────────────────────────────────────────────────────────────

def _load_all_sessions(jsonl_path: Optional[Path] = None) -> list[dict]:
    """Load all session records from the JSONL log."""
    if jsonl_path is None:
        jsonl_path = config.data_dir() / SESSIONS_JSONL
    if not jsonl_path.exists():
        return []
    records = []
    with open(jsonl_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                log.warning("sessions_jsonl: skipping malformed line — %s", exc)
    return records


def _compute_aggregate(sessions: list[dict]) -> dict:
    """Compute aggregate stats from all session records.

    Returns a dict for thetadata_tape sub-key update.
    """
    sessions_n = len(sessions)
    # Only 'ok' or 'dry_run' sessions count toward passing — no_data/insufficient_n do not
    measurable = [s for s in sessions if s.get("status") in ("ok", "dry_run")]
    sessions_passed = sum(1 for s in measurable if s.get("pass") is True)

    # Any measured (non-dry-run) fail → suspend
    real_fails = [s for s in measurable
                  if s.get("status") == "ok" and s.get("pass") is False]

    # Condition coverage
    vix_vals = [s["vix_close"] for s in measurable if s.get("vix_close") is not None]
    has_high_vix = any(v >= VIX_HIGH_THRESHOLD for v in vix_vals)
    has_calm = any(v < VIX_HIGH_THRESHOLD for v in vix_vals)

    all_roots: set[str] = set()
    for s in measurable:
        all_roots.update(s.get("roots") or [])
    multi_root = len(all_roots) >= ROOTS_NEEDED

    all_moneyness: set[str] = set()
    for s in measurable:
        all_moneyness.update(s.get("moneyness_buckets") or [])
    multi_moneyness = len(all_moneyness) >= 2

    all_expiries: set[str] = set()
    for s in measurable:
        all_expiries.update(s.get("expiries_covered") or [])
    multi_expiry = len(all_expiries) >= 2

    conditions_covered = {
        "high_vix": has_high_vix,
        "calm": has_calm,
        "multi_root": multi_root,
        "multi_expiry": multi_expiry,
        "multi_moneyness": multi_moneyness,
    }

    # production_ready: >=5 ok sessions passing, high-VIX AND calm, multi-root,
    # multi-expiry, multi-moneyness, zero real failures.
    # Per RUL-F3.12: ">=5 sessions spanning high-VIX and calm, multiple
    # roots/expiries/moneyness."  All six conditions are required.
    production_ready = (
        sessions_passed >= SESSIONS_NEEDED
        and has_high_vix
        and has_calm
        and multi_root
        and multi_expiry
        and multi_moneyness
        and len(real_fails) == 0
    )

    # Suspend logic: any measured fail suspends direction_reliable_tape
    if real_fails:
        direction_reliable_tape = False
        suspend_reason = (
            f"{len(real_fails)} session(s) failed agreement bar "
            f"(agreement_ok=False or recovery_ok=False). "
            "Manual review required before resuming. "
            f"Failed dates: {[s['date'] for s in real_fails]}"
        )
    else:
        # Read existing direction_reliable_tape from gate (preserve if already set)
        gate_path = config.data_dir() / SIGNING_GATE
        existing_tape_key = {}
        if gate_path.exists():
            try:
                existing_gate = json.loads(gate_path.read_text())
                existing_tape_key = existing_gate.get("thetadata_tape") or {}
            except Exception:  # noqa: BLE001
                pass
        direction_reliable_tape = existing_tape_key.get("direction_reliable_tape", False)
        suspend_reason = None

    last_session = sessions[-1] if sessions else None

    return {
        "sessions_n": sessions_n,
        "sessions_measurable": len(measurable),
        "sessions_passed": sessions_passed,
        "conditions_covered": conditions_covered,
        "all_roots_covered": sorted(all_roots),
        "last_session": (last_session or {}).get("date"),
        "last_session_window": (
            f"{last_session['window_start']}–{last_session['window_end']}"
            if last_session else None
        ),
        "direction_reliable_tape": direction_reliable_tape,
        "production_ready": production_ready,
        **({"suspend_reason": suspend_reason} if suspend_reason else {}),
        "production_ready_criteria": {
            "sessions_ok_needed": SESSIONS_NEEDED,
            "high_vix_needed": True,
            "calm_needed": True,
            "multi_root_needed": True,
            "multi_expiry_needed": True,
            "multi_moneyness_needed": True,
            "zero_fails_needed": True,
        },
        "bar_agreement": AGREEMENT_BAR,
        "bar_recovery": RECOVERY_BAR,
        "updated": datetime.now(timezone.utc).isoformat(),
        "note": (
            "Tape-sourced (trade+NBBO) calibration. "
            "Root direction_reliable stays false for bar sources PERMANENTLY — "
            "this sub-key is source-specific and does not grant bar signing. "
            "production_ready=True requires manual/Fable adjudication to flip "
            "any downstream consumption gate."
        ),
    }


def update_gate(jsonl_path: Optional[Path] = None, gate_path: Optional[Path] = None) -> dict:
    """Recompute thetadata_tape sub-key from all sessions and write to signing_gate.json.

    CONSTITUTION: reads all existing top-level keys, writes only thetadata_tape.
    Never touches root direction_reliable, scored, or any other root-level key.
    """
    if jsonl_path is None:
        jsonl_path = config.data_dir() / SESSIONS_JSONL
    if gate_path is None:
        gate_path = config.data_dir() / SIGNING_GATE

    sessions = _load_all_sessions(jsonl_path)
    aggregate = _compute_aggregate(sessions)

    # Load existing gate (may not exist)
    existing_gate: dict = {}
    if gate_path.exists():
        try:
            existing_gate = json.loads(gate_path.read_text())
        except Exception:  # noqa: BLE001
            existing_gate = {}

    # Snapshot existing top-level keys (excluding thetadata_tape) for invariant check
    root_snapshot = {k: json.dumps(v, sort_keys=True)
                     for k, v in existing_gate.items()
                     if k != "thetadata_tape"}

    # Build new thetadata_tape block.
    #
    # IMPORTANT: the pre-existing thetadata_tape sub-key may contain stale single-session
    # scalars from the ratified #1292 measurement (per_trade_agreement=0.8848,
    # net_sign_recovery=0.8, n_trades=16366, acceptance_criteria, status='measured',
    # window=...).  These scalars must NOT sit at the same level as the multi-session
    # aggregate — a consumer reading thetadata_tape.per_trade_agreement=0.8848 /
    # acceptance_criteria.agreement_ok=true would silently contradict an active suspend.
    #
    # Resolution: move any pre-existing single-session scalars into a nested sub-key
    # 'single_session_ratified', then write the aggregate at the top level of
    # thetadata_tape.  The aggregate keys (sessions_passed, direction_reliable_tape,
    # suspend_reason, production_ready, conditions_covered, …) are the authoritative
    # current state for any downstream consumer.
    existing_td = dict(existing_gate.get("thetadata_tape") or {})

    # Keys that belong to the single-session ratified measurement (not aggregate keys)
    _SINGLE_SESSION_KEYS = {
        "status", "insufficient_n", "asof", "generated", "signing_source",
        "n_trades", "n_contracts", "min_n_trades", "window",
        "per_trade_agreement", "per_trade_size_weighted", "net_sign_recovery",
        "acceptance_criteria", "direction_reliable_tape", "note",
        "calibration_contracts",
    }
    # Aggregate keys produced by _compute_aggregate — these win unconditionally
    _AGGREGATE_KEYS = {
        "sessions_n", "sessions_measurable", "sessions_passed", "conditions_covered",
        "all_roots_covered", "last_session", "last_session_window",
        "direction_reliable_tape", "production_ready", "suspend_reason",
        "production_ready_criteria", "bar_agreement", "bar_recovery", "updated", "note",
    }

    # Preserve any existing single-session scalars under single_session_ratified
    # (only if they are not already stashed there and only if they don't conflict
    #  with aggregate keys — e.g. direction_reliable_tape belongs to aggregate).
    single_session_snapshot = {
        k: v for k, v in existing_td.items()
        if k in _SINGLE_SESSION_KEYS and k not in _AGGREGATE_KEYS and k != "single_session_ratified"
    }
    # Merge: start from existing sub-key (to keep any unknown keys), apply aggregate on top
    new_td = dict(existing_td)
    if single_session_snapshot:
        # Stash pre-existing single-session scalars under a nested key so they are
        # still readable (for provenance) but do not conflict with the active aggregate
        existing_ratified = dict(existing_td.get("single_session_ratified") or {})
        existing_ratified.update(single_session_snapshot)
        new_td["single_session_ratified"] = existing_ratified
        # Remove the now-stashed scalars from the top level to avoid contradiction
        for k in single_session_snapshot:
            new_td.pop(k, None)
    # Unconditionally apply aggregate keys — these always override
    new_td.update(aggregate)

    new_gate = dict(existing_gate)
    new_gate["thetadata_tape"] = new_td
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    gate_path.write_text(json.dumps(new_gate, indent=2))

    # Invariant check: root keys unchanged
    written = json.loads(gate_path.read_text())
    for key, snap_val in root_snapshot.items():
        actual_val = json.dumps(written.get(key), sort_keys=True)
        if actual_val != snap_val:
            raise RuntimeError(
                f"update_gate: BUG — root key '{key}' was altered. "
                f"Before={snap_val!r}, After={actual_val!r}"
            )

    log.info("gate_update: sessions_n=%d, sessions_passed=%d, production_ready=%s",
             aggregate["sessions_n"], aggregate["sessions_passed"],
             aggregate["production_ready"])
    return aggregate


# ────────────────────────────────────────────────────────────────────────────
# Session plan
# ────────────────────────────────────────────────────────────────────────────

# Pre-defined session plan spanning required conditions.
# high-VIX: 2025-04-07 (VIX≈47), 2025-04-08 (VIX≈52)
# calm:     2024-12-16 (VIX≈15), 2024-06-18 (VIX~13), 2025-01-14 (VIX~18)
# Multi-root: each session has SPY + QQQ; one has NVDA as single-name
SESSION_PLAN = [
    {
        "date": "2025-04-07",
        "window_start": "14:30",
        "window_end": "14:50",
        "roots": ["SPY", "QQQ"],
        "description": "High-VIX session — tariff shock day (VIX≈47)",
    },
    {
        "date": "2025-04-08",
        "window_start": "14:30",
        "window_end": "14:50",
        "roots": ["SPY", "QQQ", "NVDA"],
        "description": "High-VIX + single-name — multi-root (VIX≈52)",
    },
    {
        "date": "2024-12-16",
        "window_start": "14:30",
        "window_end": "14:50",
        "roots": ["SPY", "QQQ"],
        "description": "Calm session — pre-holiday (VIX≈15)",
    },
    {
        "date": "2025-01-14",
        "window_start": "14:30",
        "window_end": "14:50",
        "roots": ["SPY", "QQQ", "NVDA"],
        "description": "Calm + single-name (VIX≈18)",
    },
    {
        "date": "2025-02-21",
        "window_start": "14:30",
        "window_end": "14:50",
        "roots": ["SPY", "QQQ"],
        "description": "Calm session — intermediate regime (VIX≈18)",
    },
]


# ────────────────────────────────────────────────────────────────────────────
# Summary printer
# ────────────────────────────────────────────────────────────────────────────

def print_summary(sessions: list[dict]) -> None:
    """Print a human-readable summary of all sessions to stdout."""
    measurable = [s for s in sessions if s.get("status") in ("ok", "dry_run")]
    ok = [s for s in measurable if s.get("pass")]
    all_roots: set[str] = set()
    for s in measurable:
        all_roots.update(s.get("roots") or [])
    vix_vals = [s["vix_close"] for s in measurable if s.get("vix_close") is not None]
    has_high = any(v >= VIX_HIGH_THRESHOLD for v in vix_vals)
    has_calm = any(v < VIX_HIGH_THRESHOLD for v in vix_vals)

    lines = [
        "",
        "=== ThetaData Tape Calibration — Session Summary ===",
        f"  Total sessions in log     : {len(sessions)}",
        f"  Measurable sessions       : {len(measurable)}",
        f"  Sessions passing bars     : {len(ok)} / {len(measurable)}"
        f"  (agreement>={AGREEMENT_BAR}, recovery>={RECOVERY_BAR})",
        f"  Distinct roots covered    : {sorted(all_roots)}  (need >={ROOTS_NEEDED})",
        f"  High-VIX session (>=20)   : {has_high}",
        f"  Calm-day session (<20)    : {has_calm}",
        f"  Needed for production_ready: {SESSIONS_NEEDED} passing sessions",
        "",
    ]
    for i, s in enumerate(sessions):
        agr_str = f"{s.get('per_trade_agreement'):.4f}" if s.get("per_trade_agreement") is not None else "null"
        nsr_str = f"{s.get('net_sign_recovery'):.4f}" if s.get("net_sign_recovery") is not None else "null"
        regime = s.get("vix_regime", "unknown")
        pass_str = "PASS" if s.get("pass") else ("FAIL" if s.get("pass") is False else "N/A")
        lines.append(
            f"  [{i+1}] {s.get('date')} {s.get('window_start','')[-5:]}-{s.get('window_end','')[-5:]} "
            f"roots={s.get('roots',[])!r:<20} "
            f"n={s.get('n_trades',0):>6}  "
            f"agr={agr_str}  nsr={nsr_str}  "
            f"vix_regime={regime:<7}  {pass_str}  "
            f"[{s.get('status','')}]"
        )
    production_ready = (
        len(ok) >= SESSIONS_NEEDED and has_high and has_calm
        and len(all_roots) >= ROOTS_NEEDED
    )
    lines += [
        "",
        f"  PRODUCTION_READY          : {production_ready}",
        "  NOTE: direction_reliable flip requires Fable/human adjudication.",
        "        Root direction_reliable stays false for bar sources PERMANENTLY.",
        "        This harness does NOT auto-flip any root gate key.",
        "=======================================================",
        "",
    ]
    print("\n".join(lines))


# ────────────────────────────────────────────────────────────────────────────
# Public entry point: run_session
# ────────────────────────────────────────────────────────────────────────────

def run_session(
    roots: list[str],
    day: date,
    window_start: str,
    window_end: str,
    dry_run: bool = False,
    jsonl_path: Optional[Path] = None,
    gate_path: Optional[Path] = None,
    seed: int = 42,
) -> dict:
    """Run one calibration session, append to JSONL, update gate sub-key.

    Returns the session record dict.
    """
    if dry_run:
        run_result = _run_session_dry(roots, day, window_start, window_end, seed=seed)
    else:
        run_result = _run_session_live(roots, day, window_start, window_end)

    record = _build_session_record(day, window_start, window_end, roots, run_result)

    # Append to JSONL
    _append_to_jsonl(record, path=jsonl_path)

    # Update gate sub-key
    agg = update_gate(jsonl_path=jsonl_path, gate_path=gate_path)

    print_summary(_load_all_sessions(jsonl_path))

    return record


# ────────────────────────────────────────────────────────────────────────────
# CLI
# ────────────────────────────────────────────────────────────────────────────

def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="Use synthetic fixture data — no ThetaData network calls")
    ap.add_argument("--run-plan", action="store_true",
                    help="Run the pre-defined multi-session plan (SESSION_PLAN)")
    ap.add_argument("--summary", action="store_true",
                    help="Print session log summary without running a new session")
    ap.add_argument("--date", default=None,
                    help="Session date YYYY-MM-DD (default: today)")
    ap.add_argument("--start", default="14:30",
                    help="Window start time HH:MM ET (default: 14:30)")
    ap.add_argument("--end", default="14:50",
                    help="Window end time HH:MM ET (default: 14:50)")
    ap.add_argument("--roots", default="SPY,QQQ",
                    help="Comma-separated roots (default: SPY,QQQ)")
    args = ap.parse_args()

    if args.summary:
        sessions = _load_all_sessions()
        print_summary(sessions)
        return 0

    if args.run_plan:
        from collectors import thetadata as td
        if not args.dry_run and not td.reachable(connect_timeout=CONNECT_TIMEOUT):
            log.warning("ThetaTerminal not reachable — run with --dry-run or start the terminal")
            return 1
        for plan_entry in SESSION_PLAN:
            log.info("plan: running session %s roots=%s", plan_entry["date"], plan_entry["roots"])
            day = datetime.strptime(plan_entry["date"], "%Y-%m-%d").date()
            record = run_session(
                roots=plan_entry["roots"],
                day=day,
                window_start=plan_entry["window_start"],
                window_end=plan_entry["window_end"],
                dry_run=args.dry_run,
            )
            log.info("plan: session %s done — pass=%s n_trades=%d",
                     plan_entry["date"], record.get("pass"), record.get("n_trades", 0))
        return 0

    # Single session
    if args.dry_run:
        day = (datetime.strptime(args.date, "%Y-%m-%d").date()
               if args.date else date(2025, 4, 7))
    else:
        day = (datetime.strptime(args.date, "%Y-%m-%d").date()
               if args.date else date.today())

        from collectors import thetadata as td
        if not td.reachable(connect_timeout=CONNECT_TIMEOUT):
            log.warning("ThetaTerminal not reachable at http://127.0.0.1:25503 — "
                        "run with --dry-run or start ThetaTerminal v3")
            return 1

    roots = [r.strip() for r in args.roots.split(",") if r.strip()]
    record = run_session(
        roots=roots,
        day=day,
        window_start=args.start,
        window_end=args.end,
        dry_run=args.dry_run,
    )
    print(json.dumps(record, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
