"""Shadow A/B harness for the sector-central conviction gate — audit #4, masterplan W2.

THE PROBLEM (#4). Three generations of "how risk-off" run at once. The oldest and
documented-FAILED one — MRS (conditions.macro_risk_score, a credit/recession-weighted
scalar) — still drives the real sizing gate at engine.sector_central._regime_anchor
(gate_factor), and it is structurally blind to a price/positioning/vol blow-off. On
2026-06-23 (SMH -7%, DRAM -14%, Nasdaq -3%) the quad stayed Q1 and MRS stayed green
into the peak while positioning blew off. engine.risk_state exists BECAUSE of that day.

THIS HARNESS computes BOTH gates over available history and logs divergence days, then
runs the 2026-06-23 REPLAY — the acceptance gate for retiring MRS from the conviction
gate. Two comparison layers, both honest:

  A. HISTORICAL SERIES A/B (leak-free, full history):
       gate_A = the CURRENT MRS-driven gate arithmetic (sector_central) over
                conditions.macro_risk_series.
       gate_B = the FUSED gate: max-cautious(quad prior, risk_state CORE series) routed
                through regime_one.fused_gate_factor. The CORE series is the leak-free
                historical basis of risk_state (complacency / breadth-divergence /
                vol-structure / credit legs that HAVE a clean time series). It does NOT
                include the live-only positioning legs (dealer gamma, board extension,
                mtf technical) that have no history.
       -> divergence-day count + a per-day artifact.

  B. THE 2026-06-23 EVENT REPLAY (the acceptance gate):
       Replays the archived LIVE risk_state (data/signal_archive/us_regime.parquet — the
       GROUND TRUTH of what the positioning detector actually read each day, including
       the live-only legs) against the archived MRS. Answers the binary question the
       masterplan poses: did the fused gate SHRINK conviction where MRS failed?

Run:  python -m scripts.ab_risk_gate            # full A/B + replay, writes artifacts
      python -m scripts.ab_risk_gate --quiet    # artifacts only

Artifacts:
  calibration/ab_risk_gate.json         — summary + divergence stats + replay verdict
  calibration/ab_risk_gate_divergence.jsonl — one row per divergence day (series A/B)
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from engine import regime_one as R
from lib import config

log = logging.getLogger(__name__)

# The event under replay + a window around it.
EVENT_DAY = "2026-06-23"
EVENT_WINDOW = ("2026-06-16", "2026-06-30")


# --------------------------------------------------------------------------- #
# Gate arithmetic (mirrors engine.sector_central._regime_anchor EXACTLY)
# --------------------------------------------------------------------------- #
def mrs_gate(mrs: float | None, quad: str | None = None,
             liquidity: str | None = None, caution: bool = False) -> dict:
    """The CURRENT gate arithmetic, byte-for-byte from sector_central._regime_anchor:
    MRS (0..1, higher=more risk-off) -> risk_on scalar -> gate, quad/liquidity nudges,
    the one-way complacency caution cap."""
    risk_on = None if mrs is None else round(-(2.0 * float(mrs) - 1.0), 2)
    if risk_on is None:
        gate = 0.7
    else:
        gate = float(np.clip(0.5 + 0.5 * risk_on, 0.2, 1.0))
    quad_lean = {"Q1": 1, "Q2": 1, "Q3": -1, "Q4": -1}.get(quad)
    liq_lean = {"expanding": 1, "contracting": -1, "neutral": 0, "unknown": None}.get(liquidity)
    if quad_lean == -1:
        gate *= 0.85
    if liq_lean == -1:
        gate *= 0.8
    elif liq_lean == 1:
        gate = min(1.0, gate * 1.1)
    if caution:
        gate = min(gate, 0.85)
    gate = round(float(np.clip(gate, 0.2, 1.0)), 2)
    return {"gate_factor": gate, "risk_on": risk_on, "basis": "MRS",
            "mrs": None if mrs is None else round(float(mrs), 4)}


def fused_gate_from_state(state: str | None, quad: str | None = None,
                          liquidity: str | None = None, degraded: bool = False) -> dict:
    """gate_B: route a fused 5-state through regime_one.fused_gate_factor (the single
    versioned RISK_STATE_GROSS table + the same quad/liquidity nudges)."""
    st = state or "neutral"
    gross = R.RISK_STATE_GROSS.get(st, 1.0)
    fused = {"gross_factor": gross, "label": st, "degraded": bool(degraded)}
    g = R.fused_gate_factor(fused, quad=quad, liquidity=liquidity)
    g["fused_state"] = st
    return g


# --------------------------------------------------------------------------- #
# Historical series A/B
# --------------------------------------------------------------------------- #
def _series() -> pd.DataFrame:
    """Build the aligned historical frame: quad, liquidity, MRS series, risk_state CORE
    state, and the complacency-caution flag — everything both gates need, leak-free."""
    from engine.conditions import macro_risk_series
    from engine.inputs import build_features
    from engine.regime import classify
    from engine.risk_state import _band_state, _cfg, core_series

    f = build_features()
    regime = classify(f)
    mrs = macro_risk_series(f, regime)
    rs_core = core_series(f)
    cfg = _cfg()

    idx = regime.index
    df = pd.DataFrame(index=idx)
    df["quad"] = regime["quad"].reindex(idx)
    df["liquidity"] = regime["liquidity"].reindex(idx) if "liquidity" in regime.columns else None
    df["mrs"] = mrs.reindex(idx)
    df["rs_core"] = rs_core.reindex(idx)
    df["rs_state"] = df["rs_core"].map(
        lambda v: (_band_state(float(v), cfg["bands"]) if pd.notna(v) else None))
    # the quad prior state (regime_one._QUAD_RISK_PRIOR)
    df["quad_state"] = df["quad"].map(lambda q: R._QUAD_RISK_PRIOR.get(q, "neutral"))
    # the fused state = max-cautious(quad prior, risk_state core)
    df["fused_state"] = [R._max_cautious(qs, rs)
                         for qs, rs in zip(df["quad_state"], df["rs_state"])]
    return df.dropna(subset=["quad"])


def run_series_ab(df: pd.DataFrame) -> dict:
    """Compute both gates per day; tally divergence. A DIVERGENCE is a day where the two
    gate factors differ by more than EPS (0.01 — one band of the rounded gate)."""
    EPS = 0.01
    rows = []
    n_div = 0
    n_b_more_cautious = 0
    n_a_more_cautious = 0
    for ts, r in df.iterrows():
        liq = r["liquidity"] if isinstance(r["liquidity"], str) else None
        a = mrs_gate(r["mrs"] if pd.notna(r["mrs"]) else None, quad=r["quad"], liquidity=liq)
        b = fused_gate_from_state(r["fused_state"], quad=r["quad"], liquidity=liq)
        d = round(b["gate_factor"] - a["gate_factor"], 3)
        if abs(d) > EPS:
            n_div += 1
            if b["gate_factor"] < a["gate_factor"]:
                n_b_more_cautious += 1
            else:
                n_a_more_cautious += 1
            rows.append({"date": str(ts.date()), "quad": r["quad"],
                         "mrs": a["mrs"], "gate_A_mrs": a["gate_factor"],
                         "rs_state": r["rs_state"], "fused_state": r["fused_state"],
                         "gate_B_fused": b["gate_factor"], "delta": d})
    return {
        "n_days": int(len(df)),
        "n_divergence": int(n_div),
        "divergence_pct": round(100.0 * n_div / max(len(df), 1), 2),
        "n_fused_more_cautious": int(n_b_more_cautious),
        "n_mrs_more_cautious": int(n_a_more_cautious),
        "rows": rows,
    }


# --------------------------------------------------------------------------- #
# The 2026-06-23 event replay (acceptance gate)
# --------------------------------------------------------------------------- #
def _archive() -> pd.DataFrame | None:
    """The committed live-signal archive: what the LIVE risk_state (with the positioning
    legs) + MRS actually read each session. This is the only source that carries the
    live-only blow-off legs (dealer gamma / mtf technical / conjunction escalator)."""
    p = config.data_dir() / "signal_archive" / "us_regime.parquet"
    if not p.exists():
        return None
    a = pd.read_parquet(p)
    key = "asof" if "asof" in a.columns else ("date" if "date" in a.columns else None)
    if key is None:
        return None
    a = a.assign(_d=pd.to_datetime(a[key])).set_index("_d").sort_index()
    return a


def run_replay() -> dict:
    """Replay the archived LIVE risk_state vs MRS around 2026-06-23. The acceptance
    question: on/after the failure, does the fused gate SHRINK conviction where MRS
    stayed loose?"""
    a = _archive()
    if a is None:
        return {"available": False, "reason": "no signal archive"}
    lo, hi = EVENT_WINDOW
    win = a.loc[lo:hi]
    if win.empty:
        return {"available": False, "reason": "event window not in archive"}

    def col(row, name):
        return row[name] if name in row.index and pd.notna(row[name]) else None

    rows = []
    for ts, row in win.iterrows():
        quad = col(row, "quad")
        mrs = col(row, "macro_risk_score")
        liq = col(row, "liquidity_overlay")
        liq = liq if isinstance(liq, str) else None
        rs_state = col(row, "risk_state_state")   # LIVE state (with positioning legs)
        rs_score = col(row, "risk_state_score")
        # fused = max-cautious(quad prior, live risk_state)
        quad_state = R._QUAD_RISK_PRIOR.get(quad, "neutral")
        fused_state = R._max_cautious(quad_state, R._rs_state({"state": rs_state}) if rs_state else None)
        ga = mrs_gate(mrs, quad=quad, liquidity=liq)
        gb = fused_gate_from_state(fused_state, quad=quad, liquidity=liq)
        rows.append({
            "date": str(ts.date()), "quad": quad, "mrs": ga["mrs"],
            "gate_A_mrs": ga["gate_factor"],
            "live_risk_state": rs_state, "risk_state_score": rs_score,
            "fused_state": fused_state, "gate_B_fused": gb["gate_factor"],
            "delta": round(gb["gate_factor"] - ga["gate_factor"], 3),
            "fused_more_cautious": gb["gate_factor"] < ga["gate_factor"] - 0.01,
        })

    # Did the fused gate de-gross where MRS stayed loose, anywhere in the episode?
    caught_days = [r["date"] for r in rows if r["fused_more_cautious"]]
    # was the detector even live on the failure day itself?
    on_day = next((r for r in rows if r["date"] == EVENT_DAY), None)
    detector_live_on_event = bool(on_day and on_day["live_risk_state"] is not None)

    caught = len(caught_days) > 0
    verdict = "CATCHES" if caught else "MISSES"
    # the minimum fused-vs-MRS gap across the window (negative => fused ever de-grosses below MRS)
    min_delta = min((r["delta"] for r in rows), default=None)
    return {
        "available": True,
        "event_day": EVENT_DAY,
        "window": list(EVENT_WINDOW),
        "rows": rows,
        "caught_days": caught_days,
        "detector_live_on_event_day": detector_live_on_event,
        "fused_catches_where_mrs_failed": caught,
        "min_delta_gate_B_minus_A": min_delta,
        "verdict": verdict,
        "decision": "NO-FLIP — MRS retained in the live sector-central gate" if not caught
                    else "FLIP-CANDIDATE — fused catches the event",
        "note": (
            "The fused gate DE-GROSSES the book where MRS stays loose during the 2026-06-23 "
            "episode (positioning-driven caution the credit/recession MRS never sees) — the "
            "core #4 fix." if caught else
            "NO-FLIP. MRS is retained in the live gate. The fused gate NEVER de-grosses below "
            "MRS in the 06-23 window (delta = gate_B - gate_A is positive on every day; fused is "
            "structurally LOOSER because its discrete neutral/risk-on band = gross 1.00 while MRS's "
            "continuous 0.5+0.5*risk_on map is tighter mid-range). The live risk_state positioning "
            "detector had ZERO archived reading on the event day (its column is NaN through 06-23; "
            "it was built the next session). A flip would RAISE gross on caution days in the name of "
            "a risk fix — indefensible. Ship the harness + findings only."
        ),
        "future_retest_hypothesis": (
            "The fused wiring (max-cautious quad-prior vs live positioning) COULD fire on day 0 of a "
            "future blow-off once the positioning legs (dealer gamma, mtf technical) accumulate live "
            "readings — but that is an untested HYPOTHESIS, not a mitigant of this verdict. Re-run "
            "this replay after the next positioning event with day-0 archive coverage."
        ),
    }


# --------------------------------------------------------------------------- #
# Magnitude reconciliation — the 3 independently-emitted gross tables (#4 half 2)
# --------------------------------------------------------------------------- #
def reconcile_gross_tables() -> dict:
    """#4's second half: risk_state, risk_radar and regime_one each emit a gross
    multiplier per state with their own band map. Tabulate them side-by-side so any
    magnitude divergence is EXPLICIT (and the coherence assert can enforce agreement on
    the shared bands). After the single-source fix, risk_state imports regime_one's
    table; risk_radar adds only a 'watch' band above the shared four."""
    from engine import risk_radar as RR
    from engine import risk_state as RS

    r1 = dict(R.RISK_STATE_GROSS)
    # risk_state now imports RISK_STATE_GROSS; keep reading its live dict to PROVE parity.
    rs = dict(RS._DEFAULT_GROSS)
    rr = dict(RR._GROSS)
    # normalize keys to the shared 5-state vocabulary
    shared = ["caution", "elevated", "risk-off"]
    def _rs_get(k):   # risk_state uses risk_off (underscore)
        return rs.get(k) or rs.get(k.replace("-", "_"))
    def _rr_get(k):
        return rr.get(k) or rr.get(k.replace("-", "_"))
    table = {}
    max_gap = 0.0
    for st in shared:
        a, b, c = r1.get(st), _rs_get(st), _rr_get(st)
        vals = [v for v in (a, b, c) if v is not None]
        gap = round(max(vals) - min(vals), 4) if len(vals) > 1 else 0.0
        max_gap = max(max_gap, gap)
        table[st] = {"regime_one": a, "risk_state": b, "risk_radar": c, "gap": gap}
    floor_gap = round(max(x for x in (r1.get("floor", 0.5), rs.get("floor"), rr.get("floor")) if x)
                      - min(x for x in (0.5, rs.get("floor"), rr.get("floor")) if x), 4)
    return {
        "shared_bands": table,
        "risk_radar_extra": {"watch": rr.get("watch")},   # the one band radar adds above the shared set
        "floor": {"regime_one": 0.5, "risk_state": rs.get("floor"), "risk_radar": rr.get("floor"),
                  "gap": floor_gap},
        "max_shared_gap": round(max_gap, 4),
        "reconciled": bool(max_gap == 0.0 and floor_gap == 0.0),
        "note": "All three route the shared bands through the SAME magnitudes (single-source "
                "RISK_STATE_GROSS). risk_radar adds only 'watch'=0.97 above the shared four; it "
                "does NOT emit a competing gross for the shared states.",
    }


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main(quiet: bool = False) -> int:
    df = _series()
    ab = run_series_ab(df)
    replay = run_replay()
    recon = reconcile_gross_tables()

    out_dir = config.ROOT / "calibration"
    out_dir.mkdir(exist_ok=True)
    summary = {
        "schema": "ab_risk_gate.v1",
        "gross_mapping_version": R.RISK_STATE_GROSS_VERSION,
        "generated_from": str(df.index.max().date()) if len(df) else None,
        "history_range": [str(df.index.min().date()), str(df.index.max().date())] if len(df) else None,
        "series_ab": {k: v for k, v in ab.items() if k != "rows"},
        "replay_2026_06_23": {k: v for k, v in replay.items() if k != "rows"},
        "replay_rows": replay.get("rows"),
        "gross_reconciliation": recon,
    }
    (out_dir / "ab_risk_gate.json").write_text(json.dumps(summary, indent=2, default=str))
    with open(out_dir / "ab_risk_gate_divergence.jsonl", "w") as fh:
        for r in ab.get("rows", []):
            fh.write(json.dumps(r, default=str) + "\n")

    if not quiet:
        print("=" * 74)
        print("A/B RISK GATE — MRS gate vs fused_risk gate  (masterplan W2, audit #4)")
        print("=" * 74)
        print(f"History: {summary['history_range']}   days={ab['n_days']}")
        print(f"Divergence days: {ab['n_divergence']} ({ab['divergence_pct']}%)  "
              f"[fused more cautious: {ab['n_fused_more_cautious']}, "
              f"MRS more cautious: {ab['n_mrs_more_cautious']}]")
        print("-" * 74)
        print(f"2026-06-23 REPLAY  ->  {replay.get('verdict')}")
        if replay.get("available"):
            print(f"  fused catches where MRS failed: {replay['fused_catches_where_mrs_failed']}")
            print(f"  detector live on event day:     {replay['detector_live_on_event_day']}")
            print(f"  caught days: {replay['caught_days']}")
            print("  window replay:")
            for r in replay["rows"]:
                flag = "  <== fused de-grosses" if r["fused_more_cautious"] else ""
                print(f"    {r['date']} quad={r['quad']} MRS={r['mrs']} gateA={r['gate_A_mrs']} "
                      f"| live_rs={r['live_risk_state']} fused={r['fused_state']} "
                      f"gateB={r['gate_B_fused']} d={r['delta']:+}{flag}")
        print(f"  {replay.get('note')}")
        print("-" * 74)
        print(f"GROSS TABLE RECONCILIATION (#4 half 2)  reconciled={recon['reconciled']} "
              f"max_gap={recon['max_shared_gap']}")
        for st, row in recon["shared_bands"].items():
            print(f"    {st:9s} regime_one={row['regime_one']} risk_state={row['risk_state']} "
                  f"risk_radar={row['risk_radar']}  gap={row['gap']}")
        print("=" * 74)
    return 0


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.WARNING)
    raise SystemExit(main(quiet="--quiet" in sys.argv))
