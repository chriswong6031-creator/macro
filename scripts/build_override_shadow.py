"""Override-Registry shadow artifact emitter (W1).

Owner-only diagnostic: compares the gated (midterm-blackout) allocation equity
curve against the ungated raw engine equity curve since gate engagement, and
provides prior-cycle context for 2014, 2018, and 2022 midterm windows.

Reads:  engine.btc_signals.compute_all() directly (never reads signals.parquet
        so it always has the fresh alloc_*_raw columns introduced by W0).
Writes: data/vector/override_shadow.json

Run directly:
    python -m scripts.build_override_shadow

Called from scripts/build_vector.py (W1 hook) after the main signal frame is
written to parquet but before final site writes — wrapped in try/except so it
NEVER breaks the build.
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Constants — midterm gate engagement date (current cycle)
# --------------------------------------------------------------------------- #
GATE_ENGAGED = "2026-01-01"

# Prior midterm windows: gate_start, election_day (hardcoded per task spec)
PRIOR_CYCLES = {
    "2014": {"gate_start": "2014-01-01", "election_day": "2014-11-04"},
    "2018": {"gate_start": "2018-01-01", "election_day": "2018-11-06"},
    "2022": {"gate_start": "2022-01-01", "election_day": "2022-11-08"},
}


# --------------------------------------------------------------------------- #
# Core equity builder (identical to build_vector.alloc_equity)
# --------------------------------------------------------------------------- #
def alloc_equity(close: pd.Series, alloc: pd.Series) -> pd.Series:
    """Compound the allocation against BTC daily returns.

    Uses alloc.shift(1) convention: today's position is set by yesterday's
    allocation signal (no look-ahead).
    """
    ret = close.pct_change().fillna(0)
    pos = alloc.shift(1).reindex(ret.index).ffill().fillna(0)
    return (1 + pos * ret).cumprod()


# --------------------------------------------------------------------------- #
# Main shadow computation
# --------------------------------------------------------------------------- #
def compute_shadow(sig: pd.DataFrame) -> dict:
    """Build the owner-only shadow artifact from the full signal frame.

    Parameters
    ----------
    sig : pd.DataFrame
        Full output of engine.btc_signals.compute_all() — must contain
        ``close``, ``alloc_optimal`` (gated), ``alloc_optimal_raw`` (pure).

    Returns
    -------
    dict
        The override_shadow payload, ready for JSON serialisation.
    """
    sig.index = pd.to_datetime(sig.index)
    today = pd.Timestamp(date.today())

    close = sig["close"]
    alloc_gated = sig["alloc_optimal"]
    alloc_raw = sig["alloc_optimal_raw"]

    # ---------------------------------------------------------------------- #
    # 1. Current-cycle window: GATE_ENGAGED → today
    # ---------------------------------------------------------------------- #
    gate_dt = pd.Timestamp(GATE_ENGAGED)
    days_since_gate = (today - gate_dt).days

    # Slice from gate date onward
    mask_current = sig.index >= gate_dt
    close_cur = close[mask_current]
    gated_cur = alloc_gated[mask_current]
    raw_cur = alloc_raw[mask_current]

    # Compute equity curves (starts at 1.0 on gate_dt)
    eq_gated_full = alloc_equity(close_cur, gated_cur)
    eq_raw_full = alloc_equity(close_cur, raw_cur)

    # Rebase both to 1.0 at the first available date on/after gate_dt
    rebase_gated = eq_gated_full.iloc[0] if len(eq_gated_full) else 1.0
    rebase_raw = eq_raw_full.iloc[0] if len(eq_raw_full) else 1.0
    eq_gated = eq_gated_full / rebase_gated
    eq_raw = eq_raw_full / rebase_raw

    gated_final = float(eq_gated.iloc[-1]) if len(eq_gated) else 1.0
    raw_final = float(eq_raw.iloc[-1]) if len(eq_raw) else 1.0
    cum_gap_pct = (raw_final - gated_final) / gated_final * 100

    # Weekly downsampled series
    weekly_gated = eq_gated.resample("W").last()
    weekly_raw = eq_raw.resample("W").last()
    weekly_idx = weekly_gated.index.union(weekly_raw.index)
    weekly_series = []
    for dt in weekly_idx:
        g = weekly_gated.get(dt)
        r = weekly_raw.get(dt)
        if pd.notna(g) and pd.notna(r):
            weekly_series.append({
                "date": dt.strftime("%Y-%m-%d"),
                "gated_equity": round(float(g), 6),
                "raw_equity": round(float(r), 6),
            })

    current_gated_alloc = float(alloc_gated.iloc[-1])
    current_raw_alloc = float(alloc_raw.iloc[-1])

    # ---------------------------------------------------------------------- #
    # 2. Prior-cycle context: 2014, 2018, 2022
    # ---------------------------------------------------------------------- #
    prior_cycles_out: dict[str, dict] = {}
    framing_parts: list[str] = []

    for yr, window in PRIOR_CYCLES.items():
        gate_start = pd.Timestamp(window["gate_start"])
        election_day = pd.Timestamp(window["election_day"])

        # "same_days" = days elapsed in the current cycle (as a reference length)
        same_days = days_since_gate

        # Point in the prior year that is same_days in from Jan 1
        same_point_dt = gate_start + timedelta(days=same_days)
        # Cap at election day (can't go beyond the gate window)
        same_point_dt = min(same_point_dt, election_day)

        # Raw engine equity in that prior year window: gate_start → same_point_dt
        mask_prior_same = (sig.index >= gate_start) & (sig.index <= same_point_dt)
        close_prior_same = close[mask_prior_same]
        raw_prior_same = alloc_raw[mask_prior_same]

        if len(close_prior_same) < 2:
            log.warning("prior cycle %s: insufficient data for same-point window", yr)
            prior_cycles_out[yr] = {
                "same_point_raw_gap_pct": None,
                "full_window_raw_return_pct": None,
                "btc_window_return_pct": None,
                "gate_verdict": "unknown",
            }
            continue

        eq_prior_same = alloc_equity(close_prior_same, raw_prior_same)
        rebase_ps = eq_prior_same.iloc[0]
        eq_prior_same_rebased = eq_prior_same / rebase_ps
        raw_at_same_point = float(eq_prior_same_rebased.iloc[-1])
        # Gated equity in prior year = 1.0 (flat cash), so gap = raw - 1.0
        same_point_gap_pct = (raw_at_same_point - 1.0) * 100

        # Full window: gate_start → election_day (raw engine total return)
        mask_full = (sig.index >= gate_start) & (sig.index <= election_day)
        close_full = close[mask_full]
        raw_full = alloc_raw[mask_full]

        if len(close_full) < 2:
            full_raw_return_pct = None
            btc_return_pct = None
            gate_verdict = "unknown"
        else:
            eq_full_prior = alloc_equity(close_full, raw_full)
            rebase_fp = eq_full_prior.iloc[0]
            eq_full_rebased = eq_full_prior / rebase_fp
            full_raw_return_pct = (float(eq_full_rebased.iloc[-1]) - 1.0) * 100

            # BTC spot return in the same window (HODL)
            btc_start = float(close_full.iloc[0])
            btc_end = float(close_full.iloc[-1])
            btc_return_pct = (btc_end / btc_start - 1.0) * 100

            gate_verdict = "saved" if full_raw_return_pct < 0 else "cost"

        prior_cycles_out[yr] = {
            "same_point_raw_gap_pct": round(same_point_gap_pct, 2) if same_point_gap_pct is not None else None,
            "full_window_raw_return_pct": round(full_raw_return_pct, 2) if full_raw_return_pct is not None else None,
            "btc_window_return_pct": round(btc_return_pct, 2) if btc_return_pct is not None else None,
            "gate_verdict": gate_verdict,
        }

        if full_raw_return_pct is not None:
            verdict_str = "gate SAVED money" if gate_verdict == "saved" else "gate COST money"
            pos_str = f"raw +{same_point_gap_pct:.1f}% ahead" if same_point_gap_pct >= 0 else f"raw {same_point_gap_pct:.1f}% (trailing gated cash)"
            framing_parts.append(
                f"{yr}: {pos_str} at same point, "
                f"full window raw={full_raw_return_pct:+.1f}% → {verdict_str}"
            )

    saved_count = sum(1 for c in prior_cycles_out.values() if c.get("gate_verdict") == "saved")
    cost_count = sum(1 for c in prior_cycles_out.values() if c.get("gate_verdict") == "cost")
    framing_note = (
        f"n=3 path shapes. At this point ({days_since_gate}d into gate), "
        f"current raw is {cum_gap_pct:+.1f}% vs gated (cash). "
        + " | ".join(framing_parts)
        + f". Gate saved in {saved_count}/3, cost in {cost_count}/3 prior cycles. "
        "No action recommended."
    )

    # ---------------------------------------------------------------------- #
    # 3. Assemble payload
    # ---------------------------------------------------------------------- #
    return {
        "audience": "owner-only",
        "as_of": today.strftime("%Y-%m-%d"),
        "gate_engaged": GATE_ENGAGED,
        "days_since_gate": days_since_gate,
        "current_ungated_alloc": round(current_raw_alloc, 4),
        "current_gated_alloc": round(current_gated_alloc, 4),
        "cum_gap_pct": round(cum_gap_pct, 2),
        "gated_equity_final": round(gated_final, 6),
        "raw_equity_final": round(raw_final, 6),
        "weekly_series": weekly_series,
        "prior_cycles": prior_cycles_out,
        "framing_note": framing_note,
    }


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def build(sig: pd.DataFrame | None = None) -> dict:
    """Compute and write the override shadow artifact.

    Parameters
    ----------
    sig : pd.DataFrame, optional
        Pre-computed signal frame.  If None, calls compute_all() directly.

    Returns
    -------
    dict
        The written payload.
    """
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

    if sig is None:
        from engine import btc_signals
        log.info("override_shadow: calling compute_all() (may take a few minutes)…")
        sig = btc_signals.compute_all()

    shadow = compute_shadow(sig)

    from lib import config
    out_dir = config.data_dir() / "vector"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "override_shadow.json"

    # MERGE, don't clobber: build_vector writes the W3 v0 payload (the admin
    # BTC Override panel's schema) just before calling us. Overlay the W1
    # measured fields onto it — panel keys preserved, stub -> measured. If no
    # v0 payload exists (standalone run), write the measured payload alone.
    payload = shadow
    if out_path.exists():
        try:
            base = json.loads(out_path.read_text())
            if isinstance(base, dict) and base.get("schema", "").startswith("override_shadow"):
                base.update({k: v for k, v in shadow.items()})
                base["schema"] = "override_shadow.v1"
                base["stub"] = False
                base["stub_note"] = ("v1: W1 measured overlay merged onto the W3 panel payload "
                                     "(weekly gated-vs-raw series, prior-cycle same-point context, "
                                     "cum gap). Per-cycle attribution + breakeven fan live in "
                                     "data/vector/gate_attribution.json.")
                payload = base
        except Exception as merge_err:  # noqa: BLE001 — fall back to standalone write
            log.warning("override_shadow: v0 merge failed (%s); writing standalone", merge_err)
    out_path.write_text(json.dumps(payload, indent=2, default=str))
    log.info("override_shadow: wrote %s (schema=%s)", out_path, payload.get("schema"))

    return payload


def _headline(shadow: dict) -> str:
    """Format a one-line headline summary for stdout."""
    lines = [
        "=== BTC Override Shadow (W1) ===",
        f"  As of            : {shadow['as_of']}",
        f"  Gate engaged     : {shadow['gate_engaged']}  ({shadow['days_since_gate']} days ago)",
        f"  Gated alloc      : {shadow['current_gated_alloc']:.0%}  (cash — gate active)",
        f"  Raw engine alloc : {shadow['current_ungated_alloc']:.0%}",
        f"  Gated equity     : {shadow['gated_equity_final']:.4f}x  (since gate)",
        f"  Raw equity       : {shadow['raw_equity_final']:.4f}x  (since gate)",
        f"  Cumulative gap   : {shadow['cum_gap_pct']:+.2f}%  (raw minus gated)",
        "",
        "  Prior-cycle context:",
    ]
    for yr, c in shadow["prior_cycles"].items():
        gap = c.get("same_point_raw_gap_pct")
        full = c.get("full_window_raw_return_pct")
        btc = c.get("btc_window_return_pct")
        verdict = c.get("gate_verdict", "?")
        lines.append(
            f"    {yr}: raw@same_point={gap:+.1f}%  full_window={full:+.1f}%  "
            f"BTC={btc:+.1f}%  → gate {verdict.upper()}"
            if all(v is not None for v in [gap, full, btc])
            else f"    {yr}: insufficient data"
        )
    lines.append("")
    lines.append(f"  {shadow['framing_note']}")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    shadow = build()
    print(_headline(shadow))
    sys.exit(0)
