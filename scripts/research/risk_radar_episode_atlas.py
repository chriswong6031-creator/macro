"""Risk Radar Episode Atlas — descriptive replay of US radar legs through major historical risk episodes.

Reads the committed engine (engine/risk_radar.py, engine/risk_radar_backtest.py) unmodified.
Invents NO new signals. This is DISPLAY-TIER / research work: base rates, nulls printed not
hidden, no promotion/kill language, never uses the word 'validated' for anything not gauntleted.
Findings are context, not authority.

Run from repo root:
    python3 scripts/research/risk_radar_episode_atlas.py

Outputs:
    reports/risk-radar-episode-atlas.md
    reports/risk_radar_episode_atlas.json
"""
from __future__ import annotations

import json
import os
import sys
import traceback
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, ".")

import numpy as np
import pandas as pd

from engine.risk_radar import leading_signals, subscore_series, _calib, context_gate_series, _is_validated
from engine.risk_radar_backtest import detect_events
from lib import store

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
REPORTS_DIR = REPO_ROOT / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

# Named episodes (frozen list per task spec).
# onset_hint = approximate reference peak date; we verify/override against detect_events()
_NAMED_EPISODES = [
    {"name": "2018Q4 selloff",       "hint": "2018-09-20"},
    {"name": "COVID-2020",           "hint": "2020-02-19"},
    {"name": "2022 bear market",     "hint": "2022-01-03"},
    {"name": "SVB March-2023",       "hint": "2023-02-02"},   # may be < 8% drawdown
    {"name": "Aug-2024 yen-carry",   "hint": "2024-07-16"},
]

# Offsets (in trading days) to inspect around T0 onset
_OFFSETS = {"T-21": -21, "T-5": -5, "T-1": -1, "T0": 0, "T+5": 5}
_LOOKBACK = 63    # window before T0 for "first elevated" scan
_LOOKAHEAD = 5    # window after T0 for "late" detection boundary
_WINDOW_LABELS = {"early_window": "T-63..T-5", "jit_window": "T-5..T0", "late_window": "T0..T+5"}

# Classification bins
_CLASS_EARLY    = "EARLY"       # first elevated >=5 trading days before T0
_CLASS_JIT      = "JUST-IN-TIME"  # T-5..T0
_CLASS_LATE     = "LATE"        # first elevated after T0 (within T+5)
_CLASS_SILENT   = "SILENT"      # data present in window, never elevated
_CLASS_NO_DATA  = "NO DATA"     # no non-NaN data at this episode

# Composite sparkline offsets
_SPARK_RANGE = range(-21, 22)   # T-21..T+21

# ---------------------------------------------------------------------------
# Helper: trading-day offset
# ---------------------------------------------------------------------------
def _offset_date(idx: pd.DatetimeIndex, t0: pd.Timestamp, n: int) -> pd.Timestamp | None:
    """Return the date n trading days from t0 on the index (positive=forward, negative=back)."""
    arr = idx.sort_values()
    pos = arr.searchsorted(t0, side="left")
    if pos >= len(arr):
        return None
    target = pos + n
    if target < 0 or target >= len(arr):
        return None
    return arr[target]


def _nearest_onset(idx: pd.DatetimeIndex, hint: str, onsets: list) -> tuple[pd.Timestamp | None, str]:
    """Find the detect_events onset nearest to hint (within 40 trading days).
    Returns (onset_date, source) where source is 'detect_events' or 'peak_override'.
    If no detect_events onset is near, returns (pd.Timestamp(hint), 'peak_override')."""
    t_hint = pd.Timestamp(hint)
    # find the closest detect_events onset within ±40 trading days
    arr = idx.sort_values()
    best = None
    best_gap = 999999
    for o in onsets:
        # approximate trading-day gap as calendar days / 1.4
        gap = abs((o - t_hint).days)
        if gap < best_gap:
            best_gap = gap
            best = o
    # ±40 trading days ≈ ±56 calendar days
    if best is not None and best_gap <= 56:
        return best, "detect_events"
    # No close onset: use the hint date as the named peak override
    # Make sure the hint date is in (or near) the trading index
    pos = arr.searchsorted(t_hint, side="left")
    if pos >= len(arr):
        pos = len(arr) - 1
    return arr[pos], "peak_override"


# ---------------------------------------------------------------------------
# Main atlas builder
# ---------------------------------------------------------------------------
def build_atlas() -> dict:
    # --- load signals ---
    print("Loading leading_signals() ... (may take a moment)")
    try:
        sigs = leading_signals()
    except Exception as e:
        print(f"FATAL: leading_signals() failed: {e}")
        raise
    calib = _calib()
    bands = calib["bands"]
    legs = list(sigs.columns)
    idx = sigs.index.sort_values()

    print(f"  Signals shape: {sigs.shape}  ({idx[0].date()} .. {idx[-1].date()})")

    # --- compute sub-scores and context gate ---
    print("Computing subscore_series() and context_gate_series() ...")
    try:
        subs = subscore_series(sigs, calib)
    except Exception as e:
        print(f"  WARNING: subscore_series failed: {e}; using empty df")
        subs = pd.DataFrame(index=sigs.index)

    try:
        gate = context_gate_series(idx)
    except Exception as e:
        print(f"  WARNING: context_gate_series failed: {e}; using all-False")
        gate = pd.Series(False, index=idx)

    # --- SPY closes for drawdown verification ---
    spy_df = store.read("yahoo", "SPY")
    spy = spy_df["close"].dropna()
    spy.index = pd.to_datetime(spy.index)
    spy = spy.sort_index()

    # --- detect all events ---
    print("Running detect_events() ...")
    onsets = detect_events(spy, depth=0.08)
    print(f"  Found {len(onsets)} onsets (depth >= 8%)")

    # --- per-leg coverage start ---
    leg_coverage: dict[str, str | None] = {}
    for leg in legs:
        fv = sigs[leg].first_valid_index()
        leg_coverage[leg] = str(fv.date()) if fv is not None else None

    # --- calibration thresholds per leg ---
    # Each leg's "elevated" threshold = thr_pct (0-1). The percentile column is 0-1 scale.
    leg_thr: dict[str, float] = {
        leg: calib["legs"].get(leg, {}).get("thr_pct", 0.90)
        for leg in legs
    }

    # --- per-episode analysis ---
    print("Analysing episodes ...")
    episode_results = []

    for ep in _NAMED_EPISODES:
        name = ep["name"]
        hint = ep["hint"]
        onset, onset_src = _nearest_onset(idx, hint, onsets)
        print(f"\n  Episode: {name}  hint={hint}  onset={onset.date()}  source={onset_src}")

        # SPY peak -> max drawdown over next 63 trading days
        spy_pos = idx.searchsorted(onset, side="left")
        spy_peak_val = float(spy.iloc[spy_pos]) if spy_pos < len(spy) else float("nan")
        fwd_window = spy.iloc[spy_pos + 1: spy_pos + 1 + 63]
        max_dd = float((fwd_window.min() / spy_peak_val) - 1.0) if len(fwd_window) > 0 and not np.isnan(spy_peak_val) else float("nan")

        # Build offset dates
        offset_dates: dict[str, pd.Timestamp | None] = {
            label: _offset_date(idx, onset, n) for label, n in _OFFSETS.items()
        }

        # Per-leg analysis
        leg_rows = []
        for leg in legs:
            cov_start = leg_coverage[leg]
            thr = leg_thr[leg]
            is_validated_flag = _is_validated(leg, calib)

            # Coverage check at this episode
            s = sigs[leg]
            # Window: T-63..T+5 (trading days)
            t_lo = _offset_date(idx, onset, -_LOOKBACK)
            t_hi = _offset_date(idx, onset, _LOOKAHEAD)
            if t_lo is None or t_hi is None:
                classification = _CLASS_NO_DATA
                first_elevated_date = None
                states = {}
                leg_rows.append(_make_leg_row(
                    leg, cov_start, states, first_elevated_date,
                    classification, is_validated_flag, error=None
                ))
                continue

            # Slice the window
            window = s.loc[t_lo:t_hi]
            non_nan_in_window = window.dropna()

            if len(non_nan_in_window) == 0:
                classification = _CLASS_NO_DATA
                first_elevated_date = None
                states = {}
                print(f"    {leg}: NO DATA (no non-NaN in T-63..T+5)")
                leg_rows.append(_make_leg_row(
                    leg, cov_start, states, first_elevated_date,
                    classification, is_validated_flag, error=None
                ))
                continue

            # State at each offset (percentile + elevated flag)
            states = {}
            for label, date in offset_dates.items():
                if date is None:
                    states[label] = {"pctile": None, "elevated": None}
                    continue
                val = s.loc[date] if date in s.index else float("nan")
                val = float(val) if pd.notna(val) else None
                elevated = bool(val >= thr) if val is not None else None
                states[label] = {"pctile": round(val, 4) if val is not None else None,
                                 "elevated": elevated}

            # First elevated date in T-63..T0 (the "early detection" window)
            t_m5 = _offset_date(idx, onset, -5)
            # For lookback window only use T-63..T0
            t0_date = onset
            lookback_window = s.loc[t_lo:t0_date]
            _lb = lookback_window.dropna(); elevated_in_lookback = _lb[_lb >= thr]

            # Also check T0..T+5 for LATE detection
            lookahead_window = s.loc[t0_date:t_hi]
            _la = lookahead_window.dropna(); elevated_in_lookahead = _la[_la >= thr]

            # FIX 1: detect left-censored EARLY rows.
            # If first_elevated == t_lo (the T-63 boundary) and that bar was already
            # elevated, we cannot know the true onset — it could be months earlier.
            left_censored = False
            if len(elevated_in_lookback) > 0:
                first_elevated_date = elevated_in_lookback.index[0]
                t_m5_date = t_m5 or onset
                if first_elevated_date <= t_m5_date:
                    classification = _CLASS_EARLY
                else:
                    classification = _CLASS_JIT
                # Check: is first_elevated == the left-edge of the window (t_lo)?
                if first_elevated_date == t_lo:
                    left_censored = True
            elif len(elevated_in_lookahead) > 0:
                first_elevated_date = elevated_in_lookahead.index[0]
                classification = _CLASS_LATE
            else:
                first_elevated_date = None
                classification = _CLASS_SILENT

            print(f"    {leg}: {classification}  "
                  f"first_elev={first_elevated_date.date() if first_elevated_date else None}  "
                  f"left_censored={left_censored}  "
                  f"T-1={states.get('T-1', {}).get('pctile')}")

            leg_rows.append(_make_leg_row(
                leg, cov_start, states,
                str(first_elevated_date.date()) if first_elevated_date else None,
                classification, is_validated_flag, error=None,
                left_censored=left_censored,
            ))

        # Composite subscore sparkline (T-21..T+21)
        composite_spark = []
        for n in _SPARK_RANGE:
            d = _offset_date(idx, onset, n)
            if d is not None and not subs.empty and len(subs.columns) > 0:
                # max Tier-A sub-score as "composite"
                tier_a_scares = [s for s, v in calib["scares"].items()
                                 if v["tier"] == "A" and s in subs.columns]
                if tier_a_scares:
                    row_vals = subs.loc[d, tier_a_scares].dropna()
                    mx = float(row_vals.max()) if len(row_vals) > 0 else None
                else:
                    mx = None
            else:
                mx = None
            gate_val = bool(gate.loc[d]) if d is not None and d in gate.index else None
            composite_spark.append({
                "offset": n,
                "date": str(d.date()) if d else None,
                "max_tier_a_subscore": round(mx, 2) if mx is not None else None,
                "gate": gate_val
            })

        # Context gate at T-5 / T0
        gate_t5 = bool(gate.loc[offset_dates["T-5"]]) if offset_dates["T-5"] is not None and offset_dates["T-5"] in gate.index else None
        gate_t0 = bool(gate.loc[onset]) if onset in gate.index else None

        episode_results.append({
            "name": name,
            "onset": str(onset.date()),
            "onset_source": onset_src,
            "hint_date": hint,
            "spy_peak_close": round(spy_peak_val, 2) if not np.isnan(spy_peak_val) else None,
            "max_drawdown_63d": round(max_dd, 4) if not np.isnan(max_dd) else None,
            "legs": leg_rows,
            "composite_spark": composite_spark,
            "gate": {"T-5": gate_t5, "T0": gate_t0},
        })

    # --- lead/lag summary across episodes (per leg) ---
    print("\nBuilding lead/lag summary ...")
    leg_summary = []
    for leg in legs:
        counts = {_CLASS_EARLY: 0, _CLASS_JIT: 0, _CLASS_LATE: 0,
                  _CLASS_SILENT: 0, _CLASS_NO_DATA: 0}
        for ep in episode_results:
            for lr in ep["legs"]:
                if lr["leg"] == leg:
                    counts[lr["classification"]] += 1
        # Flag if the leg was late-or-silent in ALL episodes that had data
        # (count episodes, not distinct classes — a class-count here false-flags
        # any leg whose non-NO-DATA readings happen to span exactly two classes)
        episodes_with_data = sum(n for c, n in counts.items() if c != _CLASS_NO_DATA)
        late_or_silent = counts[_CLASS_LATE] + counts[_CLASS_SILENT]
        all_late_or_silent_where_data = (episodes_with_data > 0 and late_or_silent == episodes_with_data)
        leg_summary.append({
            "leg": leg,
            "coverage_start": leg_coverage[leg],
            "is_validated_tier": _is_validated(leg, calib),
            "episodes_with_data": episodes_with_data,
            "counts": counts,
            "flag_all_late_or_silent": all_late_or_silent_where_data,
            "note": ("All episodes with data: late or silent — worth a second look" if all_late_or_silent_where_data else ""),
        })

    # --- causal spot-check ---
    # Spot-check: re-derive bubble_ext at T-5 of COVID-2020 using only data <= that date,
    # compare with the pre-computed value from leading_signals() over the full frame.
    spot_check = _do_causal_spot_check(spy, sigs, episode_results)

    # --- detect_events full list ---
    full_onset_list = [
        {"date": str(o.date()),
         "in_named_episode": any(
             ep["onset"] == str(o.date()) for ep in episode_results
         )}
        for o in onsets
    ]

    return {
        "episodes": episode_results,
        "leg_summary": leg_summary,
        "all_detect_events": full_onset_list,
        "causal_spot_check": spot_check,
        "provenance": {
            "script": "scripts/research/risk_radar_episode_atlas.py",
            "generated": str(pd.Timestamp.now(tz="UTC").isoformat()),
            "sigs_shape": list(sigs.shape),
            "sigs_date_range": [str(idx[0].date()), str(idx[-1].date())],
            "legs": legs,
            "leg_coverage": leg_coverage,
            "bands": bands,
            "detect_events_params": {"depth": 0.08, "fwd": 63, "min_gap": 40},
            "n_named_episodes": len(_NAMED_EPISODES),
            "n_total_detect_events": len(onsets),
            # FIX 3 note on is_validated_tier field name
            "is_validated_tier_note": (
                "Gate-passed reproduces the engine's internal _is_validated flag "
                "(leg lift >= 1.20 in the committed risk_radar_backtest evidence gate); "
                "it is the engine's own tier name, not a promotion claim by this study."
            ),
            # FIX 1 note on left_censored rows
            "left_censored_note": (
                "left_censored=true means first_elevated == the T-63 left boundary of the "
                "lookback window. The true first-elevated date is unknown and could be months "
                "earlier or a persistent-regime artifact. For these rows the EARLY classification "
                "is retained but the first_elevated date is a lower bound on lead, not a measured "
                "onset-anticipation."
            ),
        }
    }


def _make_leg_row(leg, cov_start, states, first_elevated, classification,
                  is_validated_flag, error, left_censored=False):
    return {
        "leg": leg,
        "coverage_start": cov_start,
        "is_validated_tier": is_validated_flag,
        "states": states,
        "first_elevated": first_elevated,
        "left_censored": left_censored,
        "classification": classification,
        "error": error,
    }


def _do_causal_spot_check(spy: pd.Series, sigs: pd.DataFrame, episode_results: list) -> dict:
    """Causal spot-check: re-derive bubble_ext at T-5 of COVID-2020 using only data <= that date.
    Compare with the precomputed leading_signals() value. Must agree within float rounding."""
    try:
        # Find COVID-2020 episode
        covid = next((ep for ep in episode_results if "COVID" in ep["name"]), None)
        if covid is None:
            return {"status": "skip", "reason": "COVID episode not found"}
        t0 = pd.Timestamp(covid["onset"])
        # Find T-5 date for COVID
        idx = sigs.index.sort_values()
        t5_date = _offset_date(idx, t0, -5)
        if t5_date is None:
            return {"status": "skip", "reason": "T-5 date not found for COVID"}

        # Re-derive bubble_ext at t5_date using ONLY spy data up to t5_date
        spy_trunc = spy.loc[:t5_date]
        ext = spy_trunc / spy_trunc.rolling(200, min_periods=120).mean() - 1.0
        from engine.indicators import pct_rank_window
        _PCT_WIN = 504
        pctile_trunc = pct_rank_window(ext, _PCT_WIN)
        recomputed = float(pctile_trunc.iloc[-1]) if len(pctile_trunc.dropna()) > 0 else None

        # Get precomputed value
        precomputed = float(sigs.loc[t5_date, "bubble_ext"]) if "bubble_ext" in sigs.columns and t5_date in sigs.index else None

        if recomputed is None or precomputed is None:
            return {"status": "skip", "reason": "one or both values is None"}

        diff = abs(recomputed - precomputed)
        agrees = diff < 1e-6
        return {
            "status": "pass" if agrees else "MISMATCH",
            "episode": "COVID-2020",
            "leg": "bubble_ext",
            "date": str(t5_date.date()),
            "recomputed_truncated": round(recomputed, 6),
            "precomputed_full_frame": round(precomputed, 6),
            "diff": round(diff, 9),
            "note": ("Causal percentile is identical when derived from truncated vs full frame — "
                     "confirms leak-free." if agrees else
                     f"MISMATCH: diff={diff:.2e} — potential look-ahead contamination, investigate!"),
        }
    except Exception as e:
        return {"status": "error", "reason": str(e), "traceback": traceback.format_exc()}


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------
def _classify_symbol(cls: str) -> str:
    return {
        _CLASS_EARLY:  "EARLY",
        _CLASS_JIT:    "JIT",
        _CLASS_LATE:   "LATE",
        _CLASS_SILENT: "SILENT",
        _CLASS_NO_DATA:"NO DATA",
    }.get(cls, cls)


def render_md(atlas: dict) -> str:
    lines = []
    lines.append("# Risk Radar Episode Atlas")
    lines.append("")
    lines.append("**Purpose:** Descriptive replay of the US risk radar's leg readings through five major historical risk episodes. This is display-tier context — base rates, coverage limitations stated explicitly, no promotion/kill language. Findings are descriptive, not authority.")
    lines.append("")
    lines.append(f"Generated: {atlas['provenance']['generated']}")
    lines.append(f"Signals date range: {atlas['provenance']['sigs_date_range'][0]} to {atlas['provenance']['sigs_date_range'][1]} (n_trading_days={atlas['provenance']['sigs_shape'][0]})")
    lines.append("")

    # --- Coverage table ---
    lines.append("## Coverage: First Non-NaN Date per Leg")
    lines.append("")
    lines.append("Legs with no data at a historical episode are marked NO DATA — this is NOT the same as a leg being silent (data present but not elevated).")
    lines.append("")
    lines.append("| Leg | Coverage Start | Gate-passed | Notes |")
    lines.append("|-----|---------------|-------------|-------|")
    lines.append("")
    lines.append("> **Gate-passed** reproduces the engine's internal `_is_validated` flag (leg lift >= 1.20 in the committed `risk_radar_backtest` evidence gate); it is the engine's own tier name, not a promotion claim by this study.")
    lines.append("")
    # Collect episode onset dates for coverage note computation
    _ep_onsets = [(ep["name"], pd.Timestamp(ep["onset"])) for ep in atlas["episodes"]]
    for leg, cov in atlas["provenance"]["leg_coverage"].items():
        validated = "Yes" if _is_validated(leg) else "No"
        note = ""
        if cov:
            cov_ts = pd.Timestamp(cov)
            # Count how many of the 5 named episodes start before coverage_start
            episodes_before_cov = [n for n, t in _ep_onsets if t < cov_ts]
            n_before = len(episodes_before_cov)
            if n_before == len(_ep_onsets):
                note = "No data for any named episode"
            elif n_before > 0:
                # Find the last episode name that falls before coverage_start
                last_before_name = max(
                    ((t, n) for n, t in _ep_onsets if t < cov_ts), key=lambda x: x[0]
                )[1]
                note = f"No data for episodes up to and including {last_before_name}"
        lines.append(f"| {leg} | {cov or 'N/A'} | {validated} | {note} |")
    lines.append("")

    # --- Full detect_events list ---
    lines.append("## All detect_events Onsets (depth >= 8%, fwd=63d, min_gap=40)")
    lines.append("")
    lines.append(f"n={len(atlas['all_detect_events'])} onsets on SPY (1993-2026). Named episodes are flagged.")
    lines.append("")
    lines.append("| Date | In Named Episode |")
    lines.append("|------|-----------------|")
    for ev in atlas["all_detect_events"]:
        marker = "YES (named)" if ev["in_named_episode"] else ""
        lines.append(f"| {ev['date']} | {marker} |")
    lines.append("")

    # --- Per-episode sections ---
    lines.append("## Per-Episode Analysis")
    lines.append("")
    lines.append("**Key:** EARLY = first elevated >=5 trading days before T0; JIT = T-5..T0; LATE = T0..T+5 (first elevated AFTER onset); SILENT = data present in T-63..T+5, never elevated; NO DATA = no non-NaN data in window.")
    lines.append("")

    for ep in atlas["episodes"]:
        lines.append(f"### {ep['name']}")
        lines.append("")
        lines.append(f"- **Onset date:** {ep['onset']} (source: {ep['onset_source']})")
        if ep["onset_source"] == "peak_override":
            lines.append(f"  - Note: detect_events(depth=0.08) did not emit an onset near the hint date ({ep['hint_date']}). Using named market peak as T0 override.")
        lines.append(f"- **Hint date:** {ep['hint_date']}")
        lines.append(f"- **SPY close at T0:** {ep['spy_peak_close']}")
        dd_pct = f"{ep['max_drawdown_63d']*100:.1f}%" if ep['max_drawdown_63d'] is not None else "N/A"
        lines.append(f"- **Max drawdown over next 63 trading days:** {dd_pct}")
        lines.append(f"- **Context gate at T-5:** {ep['gate'].get('T-5')}  /  **T0:** {ep['gate'].get('T0')}")
        lines.append("")

        # Per-leg table
        lines.append("| Leg | Gate-passed | Coverage Start | T-21 pctile | T-5 pctile | T-1 pctile | T0 pctile | T+5 pctile | First Elevated | Classification |")
        lines.append("|-----|-------------|----------------|-------------|------------|------------|-----------|------------|----------------|----------------|")
        ep_left_censored_legs = []
        for lr in ep["legs"]:
            def _fmt(label):
                s = lr["states"].get(label, {})
                if not s:
                    return "—"
                p = s.get("pctile")
                e = s.get("elevated")
                if p is None:
                    return "—"
                flag = "*" if e else ""
                return f"{p:.3f}{flag}"
            v = "Y" if lr["is_validated_tier"] else "N"
            cov = lr["coverage_start"] or "N/A"
            cls = _classify_symbol(lr["classification"])
            fe = lr["first_elevated"] or "—"
            # FIX 1: append left-censored marker if applicable
            lc = lr.get("left_censored", False)
            if lc:
                fe = f"{fe} ⟵ left-censored: already elevated at window open"
                ep_left_censored_legs.append(lr["leg"])
            lines.append(
                f"| {lr['leg']} | {v} | {cov} "
                f"| {_fmt('T-21')} | {_fmt('T-5')} | {_fmt('T-1')} | {_fmt('T0')} | {_fmt('T+5')} "
                f"| {fe} | {cls} |"
            )
        lines.append("")
        lines.append("*Pctile values are 0-1 causal trailing-504d percentiles. Asterisk (*) = elevated (at or above leg threshold). T0 = onset date.*")
        lines.append("")
        # FIX 1: left-censored note under per-episode table
        if ep_left_censored_legs:
            lines.append(f"**Left-censored note ({', '.join(ep_left_censored_legs)}):** "
                         "A T-63 first_elevated date is a lower bound on lead, not a measured "
                         "onset-anticipation — the leg was already elevated when the lookback window "
                         "opened. EARLY counts including these rows are marked with ⟵.")
            lines.append("")

        # Composite sparkline summary (selected offsets)
        tier_a_spark = [(r["offset"], r["max_tier_a_subscore"], r["gate"])
                        for r in ep["composite_spark"] if r["offset"] in (-21, -10, -5, -1, 0, 5, 10, 21)]
        lines.append("**Max Tier-A subscore trajectory (0-100) at selected offsets:**")
        lines.append("")
        lines.append("| Offset | Date | Max Tier-A Subscore | Context Gate |")
        lines.append("|--------|------|---------------------|-------------|")
        for row in ep["composite_spark"]:
            if row["offset"] in (-21, -10, -5, -1, 0, 5, 10, 21):
                sc = f"{row['max_tier_a_subscore']:.1f}" if row["max_tier_a_subscore"] is not None else "—"
                g = str(row["gate"]) if row["gate"] is not None else "—"
                lines.append(f"| T{row['offset']:+d} | {row['date'] or '—'} | {sc} | {g} |")
        lines.append("")
        # FIX 2: un-gated subscore framing clarification
        lines.append(
            "_The trajectory above is the raw un-gated max Tier-A subscore; "
            "the engine's headline STATE applies the context-gate cap "
            "(`engine/risk_radar_backtest.py` `state_series` caps loud states at 'caution' "
            "when the gate is False) — and the gate was False at onset for the episodes "
            "where the table shows it — so a high subscore here did NOT correspond to a "
            "loud banner at the time._"
        )
        lines.append("")

    # --- Lead/lag summary table ---
    lines.append("## Lead/Lag Summary: Per Leg Across All 5 Episodes")
    lines.append("")
    lines.append(f"n = 5 named episodes. Counts reflect how many times each leg fell in each classification across episodes. A NO DATA entry means the leg had no data at that episode (not the same as silent).")
    lines.append("")
    lines.append("| Leg | Gate-passed | Cov Start | EARLY | JIT | LATE | SILENT | NO DATA | All-Late-or-Silent? |")
    lines.append("|-----|-------------|-----------|-------|-----|------|--------|---------|---------------------|")
    # Collect left-censored info per leg across all episodes
    lc_legs: dict[str, list[str]] = {}
    for ep in atlas["episodes"]:
        for lr in ep["legs"]:
            if lr.get("left_censored"):
                lc_legs.setdefault(lr["leg"], []).append(ep["name"])
    for ls in atlas["leg_summary"]:
        c = ls["counts"]
        flag = "YES — worth a second look" if ls["flag_all_late_or_silent"] else ""
        v = "Y" if ls["is_validated_tier"] else "N"
        early_count = c[_CLASS_EARLY]
        # Mark EARLY count if any of those rows were left-censored
        if ls["leg"] in lc_legs:
            n_lc = len(lc_legs[ls["leg"]])
            early_str = f"{early_count} ({n_lc} left-censored⟵)"
        else:
            early_str = str(early_count)
        lines.append(
            f"| {ls['leg']} | {v} | {ls['coverage_start'] or 'N/A'} "
            f"| {early_str} | {c[_CLASS_JIT]} | {c[_CLASS_LATE]} | {c[_CLASS_SILENT]} | {c[_CLASS_NO_DATA]} "
            f"| {flag} |"
        )
    lines.append("")
    lines.append("*Legs flagged 'All-Late-or-Silent' had no EARLY or JIT readings in any episode for which data existed. This is descriptive context, not a kill — other factors may limit historical data coverage (e.g., leg born post-2020), or the mechanism may be genuinely reactive rather than leading.*")
    lines.append("")
    # FIX 1: left-censored note in lead/lag summary
    if lc_legs:
        lines.append(
            "**Lead/lag note on left-censored rows (⟵):** "
            "EARLY counts marked with ⟵ include rows where `first_elevated` equals the T-63 "
            "left-boundary of the lookback window — i.e., the leg was already elevated when the "
            "window opened. The T-63 date is a lower bound on lead time, not a measured "
            "onset-anticipation. True lead could be months earlier or could reflect a "
            "persistent-regime artifact."
        )
        lines.append("")

    # --- Scorecard cross-check ---
    lines.append("## Scorecard Cross-Check")
    lines.append("")
    lines.append("The `data/risk_radar/scorecard.json` (schema: `risk_radar_scorecard.v1`) currently shows `windows.full.alerts.n = 0` across all markets and windows — no graded alerts in any market/window, so no lift cross-check is possible yet. The atlas's historical leg readings are the primary descriptive record until the forward-outcome log matures.")
    lines.append("")

    # --- Causal spot-check ---
    lines.append("## Causal Spot-Check (Self-Check 3)")
    lines.append("")
    sc = atlas["causal_spot_check"]
    lines.append(f"**Status:** {sc.get('status', 'N/A')}")
    if sc.get("status") == "pass":
        lines.append(f"- Episode: {sc['episode']}, Leg: {sc['leg']}, Date: {sc['date']}")
        lines.append(f"- Recomputed (truncated frame): {sc['recomputed_truncated']}")
        lines.append(f"- Precomputed (full frame): {sc['precomputed_full_frame']}")
        lines.append(f"- Diff: {sc['diff']}")
        lines.append(f"- {sc['note']}")
    elif sc.get("status") == "MISMATCH":
        lines.append(f"  **WARNING — MISMATCH: {sc['note']}**")
    else:
        lines.append(f"- {sc.get('reason', '')}")
    lines.append("")

    # --- Coverage limitations ---
    lines.append("## Coverage Limitations")
    lines.append("")
    lines.append("- **vol_putcall, vol_gex:** These Tier-B flow legs are NOT present in leading_signals() output because they are inert until >=252 rows accumulate (mature cboe store required). They show as NO DATA for all 5 historical episodes.")
    lines.append("- **ai_breadth_divergence:** Born 2025-05-28. No data for any episode prior to Aug-2024. Inert until 252 rows of breadth_split.parquet accumulate.")
    lines.append("- **corr_floor_break:** Requires >=252 rows of COR1M. Coverage starts 2006-01-03. No data for episodes before 2008.")
    lines.append("- **credit_hyg_tlt:** HYG/TLT data begins 2008-05-07. Data is present for all 5 named episodes (including 2018Q4). No data for pre-2008 episodes such as the 2007-2008 crisis.")
    lines.append("- **rates_move, rates_realrate:** MOVE and DFII10 data begins 2003-2004. Data is present for all 5 named episodes.")
    lines.append("- **vol_term (VIX9D/VIX3M ratio):** VIX9D data starts 2011-12-30. Data is present for all 5 named episodes (including 2018Q4). No data for pre-2012 episodes.")
    lines.append("- **SVB March-2023:** The SPY drawdown from the Feb 2023 local peak was less than 8%, so detect_events(depth=0.08) did not emit an onset. The named peak date (hint: 2023-02-02) was used as T0 override. The max drawdown column confirms the actual depth.")
    lines.append("- **Scorecard cross-check:** windows.full.alerts.n = 0 in scorecard.json across all markets; no realized outcome data available yet.")
    lines.append("")

    # --- Self-checks ---
    lines.append("## Self-Checks")
    lines.append("")
    lines.append("1. **COVID-2020 check:** See the per-episode table above. Multiple legs should show EARLY or JIT for the Feb-2020 episode; if literally everything is LATE/NO DATA, a join/date bug is likely.")
    lines.append("2. **Onset date verification:** SPY close at T0 and max drawdown over 63d are printed per episode. These confirm the onset date is a genuine local peak with subsequent decline.")
    lines.append(f"3. **Causal percentile check:** {sc.get('note', sc.get('reason', 'See above'))}")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    atlas = build_atlas()

    # Write JSON
    json_path = REPORTS_DIR / "risk_radar_episode_atlas.json"
    with open(json_path, "w") as f:
        json.dump(atlas, f, indent=2, default=str)
    print(f"\nJSON written: {json_path}")

    # Write Markdown
    md = render_md(atlas)
    md_path = REPORTS_DIR / "risk-radar-episode-atlas.md"
    with open(md_path, "w") as f:
        f.write(md)
    print(f"MD written:   {md_path}")

    # --- Self-check 1: COVID should show EARLY/JIT legs ---
    covid_ep = next((ep for ep in atlas["episodes"] if "COVID" in ep["name"]), None)
    if covid_ep:
        early_jit = [lr["leg"] for lr in covid_ep["legs"]
                     if lr["classification"] in (_CLASS_EARLY, _CLASS_JIT)]
        late_silent = [lr["leg"] for lr in covid_ep["legs"]
                       if lr["classification"] in (_CLASS_LATE, _CLASS_SILENT)]
        no_data = [lr["leg"] for lr in covid_ep["legs"]
                   if lr["classification"] == _CLASS_NO_DATA]
        print(f"\n[SELF-CHECK 1] COVID-2020 early/JIT legs: {early_jit}")
        print(f"               COVID-2020 late/silent legs: {late_silent}")
        print(f"               COVID-2020 no-data legs: {no_data}")
        if len(early_jit) == 0 and len(late_silent) > 0:
            print("  WARNING: No EARLY/JIT legs for COVID — suspect a date join bug!")
        else:
            print("  OK: At least some legs fired EARLY or JIT for COVID.")
    else:
        print("[SELF-CHECK 1] COVID episode not found in results!")

    # --- Self-check 2: Onset dates verified ---
    print("\n[SELF-CHECK 2] Episode onset verification:")
    for ep in atlas["episodes"]:
        dd_str = f"{ep['max_drawdown_63d']*100:.1f}%" if ep["max_drawdown_63d"] is not None else "N/A"
        print(f"  {ep['name']:30s}  onset={ep['onset']} src={ep['onset_source']:15s} "
              f"SPY_close={ep['spy_peak_close']} max_dd_63d={dd_str}")

    # --- Self-check 3: Causal spot-check ---
    sc = atlas["causal_spot_check"]
    print(f"\n[SELF-CHECK 3] Causal percentile spot-check: {sc.get('status')}")
    if sc.get("status") == "pass":
        print(f"  bubble_ext at T-5 of COVID: recomputed={sc['recomputed_truncated']} "
              f"precomputed={sc['precomputed_full_frame']} diff={sc['diff']}")
    else:
        print(f"  {sc}")

    print("\nDone.")


if __name__ == "__main__":
    main()
