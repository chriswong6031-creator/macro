"""Calibration and replay harness for the 7-market international risk radars.

Research/ops tool — OFF the render path. Never imported by any build script.
Writes NOTHING (stdout only).

Usage:
    python3 -m scripts.calibrate_risk_radar_intl [--markets kr,jp,...] [--years 30]
    python3 -m scripts.calibrate_risk_radar_intl --replay MARKET \\
        --replay-from YYYY-MM-DD --replay-to YYYY-MM-DD

Calibrate mode (default):
  For each market, measures per-state P(>=5% forward drawdown within H business days)
  from the market's own history and prints:
  - Per-state day-count table with WARN for states with n < 30
  - Base rates (unconditional drawdown frequencies)
  - Ready-to-paste Python literal block: prob_base={...}, prob_cal={...}
  - Provenance comment line

Replay mode (--replay MARKET --replay-from ... --replay-to ...):
  For each session in the date range prints:
  date, comp score (0-100), gated state, ungated state, gate components
  (below_200dma / recent_parabolic), and the latest percentile of each sub-leg >= 0.55.
  Produces the KOSPI post-mortem artifact.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

# ensure repo root is on sys.path when run as -m scripts.calibrate_risk_radar_intl
_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from engine import risk_radar_intl as _rri
from engine.risk_radar_intl import (
    _STATE_ORDER, _band, _gate_series, composite_series,
    _EXT_PARABOLIC, _GATE_MEMORY,
)
from engine.risk_radar_intl_audit import HORIZONS, PRIMARY_DD

# ─── forward-outcome grading (replicates _grade_entry exactly) ────────────────

def _grade_day(B: pd.Series, i: int, horizons: dict) -> dict | None:
    """Replicate engine/risk_radar_intl_audit._grade_entry semantics exactly.
    i is the integer position on B. Returns None if the longest horizon hasn't matured."""
    maxH = max(horizons.values())
    if i + 1 + maxH > len(B):
        return None
    base_px = float(B.iloc[i])
    hit = {}
    for hk, hd in horizons.items():
        w = B.iloc[i + 1: i + 1 + hd]
        dd = float(w.min() / base_px - 1.0) if len(w) else None
        hit[hk] = dd is not None and dd <= -PRIMARY_DD
    return hit


# ─── monotone enforcement (running max along STATE_ORDER) ─────────────────────

def _enforce_monotone(state_probs: dict) -> dict:
    """Enforce monotone-increasing probabilities along calm -> risk-off."""
    result = dict(state_probs)
    running_max = 0.0
    for st in _STATE_ORDER:
        if st in result:
            val = max(result[st], running_max)
            result[st] = round(val, 3)
            running_max = val
    return result


# ─── core calibrate function (importable by tests) ───────────────────────────

def calibrate(profile: "_rri.RadarProfile", years: int = 30) -> dict | None:
    """Calibrate prob_base and prob_cal for `profile` from its own history.

    Returns a dict with keys:
      market, window_start, window_end, n_days, n_valid,
      prob_base (h5/h10/h21),
      prob_cal  (h5/h10/h21 -> {state: prob}),
      state_counts (state -> {n, n_hit_h21}),
      base_rates (h5/h10/h21 -> float)
    Returns None if insufficient data.
    """
    B, sub, comp, gate = composite_series(profile)
    if B is None or comp is None or gate is None:
        return None

    bands = profile.bands
    cutoff = B.index[-1] - pd.offsets.BDay(years * 252)
    idx_window = comp.index[comp.index >= cutoff]
    if len(idx_window) < 100:
        return None

    # need the full B for forward-outcome windows, but only calibrate from cutoff
    window_start = idx_window[0]
    window_end = idx_window[-1]

    # align comp and gate to window
    comp_w = comp.reindex(idx_window)
    gate_w = gate.reindex(idx_window).fillna(False)

    # build integer position index on B for the window (for _grade_day)
    b_arr = B.values
    b_idx = B.index

    # for each day in window, compute state and grade if matured
    state_counts: dict = {st: {"n": 0, "n_hit_h5": 0, "n_hit_h10": 0, "n_hit_h21": 0}
                          for st in _STATE_ORDER}
    base_counts = {"h5": 0, "h10": 0, "h21": 0}
    n_valid = 0

    for dt, comp_val in comp_w.items():
        gate_open = bool(gate_w.get(dt, False))
        st_ungated = _band(float(comp_val) * 100 if comp_val is not None and not np.isnan(float(comp_val)) else None, bands)
        st = st_ungated
        if not gate_open and _STATE_ORDER.index(st) > _STATE_ORDER.index("caution"):
            st = "caution"

        # find integer position on B
        try:
            loc = b_idx.get_loc(dt)
        except KeyError:
            continue
        if not isinstance(loc, (int, np.integer)):
            # e.g. slice from duplicate index — skip
            continue

        g = _grade_day(B, int(loc), HORIZONS)
        if g is None:
            continue  # not matured yet — exclude from calibration

        n_valid += 1
        state_counts[st]["n"] += 1
        for hk in ("h5", "h10", "h21"):
            if g[hk]:
                state_counts[st][f"n_hit_{hk}"] += 1
                base_counts[hk] += 1

    if n_valid == 0:
        return None

    # base rates
    prob_base = {hk: round(base_counts[hk] / n_valid, 3) for hk in ("h5", "h10", "h21")}

    # per-state RAW rates (no monotone enforcement — descriptive only)
    prob_cal_raw: dict = {"h5": {}, "h10": {}, "h21": {}}
    for st, d in state_counts.items():
        n = d["n"]
        for hk in ("h5", "h10", "h21"):
            if n > 0:
                prob_cal_raw[hk][st] = round(d[f"n_hit_{hk}"] / n, 3)

    # policy: prob_cal baked FLAT AT BASE — no in-sample lift claimed
    prob_cal: dict = {}
    for hk in ("h5", "h10", "h21"):
        base_h = prob_base[hk]
        prob_cal[hk] = {st: base_h for st in _STATE_ORDER}

    return {
        "market": profile.key,
        "window_start": str(window_start.date()),
        "window_end": str(window_end.date()),
        "n_days": len(idx_window),
        "n_valid": n_valid,
        "prob_base": prob_base,
        "prob_cal": prob_cal,
        "prob_cal_raw": prob_cal_raw,
        "state_counts": state_counts,
        "base_rates": prob_base,
    }


# ─── CLI calibrate mode ───────────────────────────────────────────────────────

def _print_calibration(profile: "_rri.RadarProfile", years: int) -> None:
    key = profile.key
    print(f"\n{'='*60}")
    print(f"MARKET: {key.upper()}")
    print(f"{'='*60}")
    result = calibrate(profile, years=years)
    if result is None:
        print(f"  [WARN] No data available for {key} — calibration skipped")
        return

    ws, we, nd, nv = result["window_start"], result["window_end"], result["n_days"], result["n_valid"]
    print(f"  Window:  {ws} .. {we}  n_days={nd}  n_valid={nv}")
    print()

    # per-state day-count table — RAW rates (no monotone enforcement)
    state_counts = result["state_counts"]
    prob_cal_raw = result["prob_cal_raw"]
    header = f"  {'State':<12} {'n':>6}  {'h5_p':>6}  {'h10_p':>7}  {'h21_p':>7}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for st in _STATE_ORDER:
        d = state_counts[st]
        n = d["n"]
        warn = "  <-- WARN n<30" if 0 < n < 30 else ""
        h5_p  = f"{prob_cal_raw['h5'].get(st, '-'):>6}" if n > 0 else "     -"
        h10_p = f"{prob_cal_raw['h10'].get(st, '-'):>7}" if n > 0 else "      -"
        h21_p = f"{prob_cal_raw['h21'].get(st, '-'):>7}" if n > 0 else "      -"
        print(f"  {st:<12} {n:>6}  {h5_p}  {h10_p}  {h21_p}{warn}")

    pb = result["prob_base"]
    print()
    print(f"  Base rates:  h5={pb['h5']}  h10={pb['h10']}  h21={pb['h21']}")

    # pooled loud-tier lift (descriptive, overlapping-window, in-sample)
    sc = state_counts
    loud_n    = sc["elevated"]["n"] + sc["risk-off"]["n"]
    loud_h5   = sc["elevated"]["n_hit_h5"]  + sc["risk-off"]["n_hit_h5"]
    loud_h10  = sc["elevated"]["n_hit_h10"] + sc["risk-off"]["n_hit_h10"]
    loud_h21  = sc["elevated"]["n_hit_h21"] + sc["risk-off"]["n_hit_h21"]
    calm_n    = sc["calm"]["n"]
    calm_h21  = sc["calm"]["n_hit_h21"]
    if loud_n > 0 and pb["h5"] > 0:
        lift_h5  = round((loud_h5  / loud_n) / pb["h5"],  2) if pb["h5"]  > 0 else None
        lift_h10 = round((loud_h10 / loud_n) / pb["h10"], 2) if pb["h10"] > 0 else None
        lift_h21 = round((loud_h21 / loud_n) / pb["h21"], 2) if pb["h21"] > 0 else None
        print(f"  Pooled loud (elevated+risk-off) lift vs base:  n={loud_n}  "
              f"h5={lift_h5}x  h10={lift_h10}x  h21={lift_h21}x")
        print(f"  [DESCRIPTIVE ONLY — overlapping forward windows, in-sample, NOT baked into prob_cal]")
    else:
        print(f"  Pooled loud (elevated+risk-off): n={loud_n} — insufficient days")
    print()

    # sanity checks
    h21_base = pb["h21"]
    if not (0.05 <= h21_base <= 0.45):
        print(f"  [SANITY FLAG] h21 base rate {h21_base} outside expected range 0.05-0.45")

    # provenance comment + paste block (FLAT AT BASE — no in-sample lift baked)
    prov = (f"# prob surfaces: base rates measured from this market's own close history by\n"
            f"  # scripts/calibrate_risk_radar_intl.py (2026-07-16, window {ws}..{we}, n_days={nd}; n counts overlapping forward windows, not independent samples).\n"
            f"  # prob_cal is seeded FLAT AT BASE: the in-sample per-state read of this ported\n"
            f"  # construction showed no (or overlap-fragile) loud-tier lift — printed by the\n"
            f"  # harness as a descriptive artifact, never baked. The live forward log + bounded\n"
            f"  # tuner (risk_radar_intl_tune, do-no-harm Brier) own the surface from n_graded>=25.")
    print()
    print("  --- PASTE BLOCK ---")
    print(f"  # prob_cal seeded FLAT AT BASE — no in-sample lift claimed (overlapping-window read is descriptive only); the live forward log + risk_radar_intl_tune own the surface from n_graded>=25.")
    print(f"  {prov}")
    print(f"  prob_base={{'h5': {pb['h5']}, 'h10': {pb['h10']}, 'h21': {pb['h21']}}},")
    # flat-at-base surface: every state gets exactly prob_base[h]
    print("  prob_cal={")
    for hk in ("h5", "h10", "h21"):
        base_h = pb[hk]
        items = ", ".join(f"'{st}': {base_h}" for st in _STATE_ORDER)
        print(f"      '{hk}':  {{{items}}},")
    print("  },")


# ─── CLI replay mode ─────────────────────────────────────────────────────────

def _print_replay(profile: "_rri.RadarProfile", from_date: str, to_date: str) -> None:
    key = profile.key
    print(f"\n{'='*60}")
    print(f"REPLAY: {key.upper()}  {from_date} -> {to_date}")
    print(f"{'='*60}")

    B, sub, comp, gate = composite_series(profile)
    if B is None or comp is None or gate is None:
        print(f"  [WARN] No data for {key}")
        return

    bands = profile.bands
    dt_from = pd.Timestamp(from_date)
    dt_to = pd.Timestamp(to_date)

    # align to available index
    session_dates = comp.index[(comp.index >= dt_from) & (comp.index <= dt_to)]
    if len(session_dates) == 0:
        print("  [WARN] No sessions in date range")
        return

    # sub-leg last values on each date
    sub_names = list(sub.keys())

    ma_B = B.rolling(200, min_periods=120).mean()

    print(f"  {'Date':<12} {'Score':>6} {'State':<10} {'Ungated':<10} {'below200':>9} {'recent_para':>12}  Firing legs (>=0.55)")
    print("  " + "-" * 95)

    for dt in session_dates:
        comp_val = comp.get(dt)
        if comp_val is None or (isinstance(comp_val, float) and np.isnan(comp_val)):
            continue
        score = round(float(comp_val) * 100, 1)
        gate_open = bool(gate.get(dt, False))
        b_200 = bool(B.get(dt, np.nan) < ma_B.get(dt, np.nan)) if not np.isnan(float(ma_B.get(dt, np.nan) if ma_B.get(dt) is not None else np.nan)) else False

        # recent_parabolic
        rp = False
        if profile.gate_mode == "below_or_recent_parabolic" and profile.ext_sources:
            ext_code = profile.ext_sources[0][2]
            ext_s = sub.get(ext_code)
            if ext_s is not None:
                # rolling max over GATE_MEMORY sessions up to dt
                ext_window = ext_s[ext_s.index <= dt].tail(_GATE_MEMORY)
                rp = bool(len(ext_window) > 0 and float(ext_window.max()) >= _EXT_PARABOLIC)

        st_ungated = _band(score, bands)
        st = st_ungated
        if not gate_open and _STATE_ORDER.index(st) > _STATE_ORDER.index("caution"):
            st = "caution"

        # firing sub-legs (pctile >= 0.55 on this date)
        firing = []
        for sn in sub_names:
            sv = sub[sn].get(dt)
            if sv is not None and not np.isnan(float(sv)) and float(sv) >= 0.55:
                firing.append(f"{sn}={float(sv):.3f}")

        date_str = str(dt.date())
        print(f"  {date_str:<12} {score:>6.1f} {st:<10} {st_ungated:<10} {str(b_200):>9} {str(rp):>12}  {', '.join(firing)}")


# ─── CLI entry point ──────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--markets", default=None,
                    help="Comma-separated market keys to calibrate (default: all 7 new markets)")
    ap.add_argument("--years", type=int, default=30,
                    help="Trailing years of history to calibrate from (default: 30)")
    ap.add_argument("--replay", default=None, metavar="MARKET",
                    help="Replay mode: market key to replay")
    ap.add_argument("--replay-from", default=None, metavar="YYYY-MM-DD",
                    help="Start date for replay")
    ap.add_argument("--replay-to", default=None, metavar="YYYY-MM-DD",
                    help="End date for replay")
    args = ap.parse_args()

    if args.replay:
        key = args.replay.lower()
        prof = _rri.PROFILES.get(key)
        if prof is None:
            print(f"ERROR: unknown market key '{key}'. Available: {list(_rri.PROFILES.keys())}")
            return 1
        from_dt = args.replay_from or "2026-01-01"
        to_dt = args.replay_to or str(date.today())
        _print_replay(prof, from_dt, to_dt)
        return 0

    # calibrate mode
    target_keys = [k.strip().lower() for k in args.markets.split(",")] if args.markets else \
        ["kr", "jp", "tw", "in", "au", "gb", "ez"]

    for key in target_keys:
        prof = _rri.PROFILES.get(key)
        if prof is None:
            print(f"[WARN] Unknown market key '{key}' — skipping")
            continue
        _print_calibration(prof, years=args.years)

    return 0


if __name__ == "__main__":
    sys.exit(main())
