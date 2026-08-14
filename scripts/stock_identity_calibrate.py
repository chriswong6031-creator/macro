#!/usr/bin/env python3
"""Freeze the W1 catalog / state / tier / zone constants on SI-SEALED-CAL-P1.

**This script refuses to run without the partition manifest**, and asserts that
every symbol it reads is a drawn calibration member. That is not defensive
politeness — it is the mechanical form of the draw-order law (registration §3/§4):

    universe snapshot -> pilot fixed -> blind drawn -> calibration drawn ->
    manifest hashes written -> ONLY THEN constants calibrated

A constant chosen before the partition sealed would be a constant chosen on the
grading data, which is exactly the ~110-free-constant hole the sealed partition
exists to close (masterplan review finding 4). Pilot/exemplar and blind names
contribute nothing here under any clause.

Two further guards, both stricter than required:

* **Recent-history guard.** Receipts read calibration history only through
  ``asof - 126 trading days``, so the §9.2 untouched-holdout window is not even
  descriptively consumed by constant-setting.
* **Component (i) only.** §4 permits pre-boundary history of undrawn pool names as
  additional material; W1 uses only the drawn names' history. Using less than the
  permitted material is strictly conservative, and it is recorded rather than
  quietly enjoyed.

Every selection rule below is written in code and in the emitted receipts **before**
its value is computed from partition data, and every declared constant is marked
``declared, not partition-computed`` so a reader can tell at a glance which numbers
the partition actually chose. The ±20% sensitivity grid is registered in the Trial
Ledger BEFORE it runs (G-7) and is diagnostic only — it never re-picks a value.

Constants never change after sealing; a revision voids the affected preregs.

Usage::

    python3 scripts/stock_identity_calibrate.py
    python3 scripts/stock_identity_calibrate.py --workers 8 --sensitivity-names 50
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import multiprocessing as mp
import sys
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from engine.stock_identity import episodes as ep_mod  # noqa: E402
from engine.stock_identity import state as state_mod  # noqa: E402
from engine.stock_identity.authority import authority_block  # noqa: E402
from engine.stock_identity.fingerprint import spec as fp_spec, spec_hash as fp_spec_hash  # noqa: E402
from engine.stock_identity.hygiene import COMPUTE_BLOCKLIST  # noqa: E402
from engine.stock_identity.plane import load_symbol  # noqa: E402
from engine.trial_ledger import TrialLedger, register_trials  # noqa: E402

log = logging.getLogger("stock_identity.calibrate")

MANIFEST_PATH = REPO_ROOT / "data" / "stock_identity" / "partition" / "partition_manifest_v1.json"
OUT_PATH = REPO_ROOT / "data" / "stock_identity" / "constants" / "si_constants_v1.json"

TRIAL_FAMILY = "stock_identity_w1_calibration"

N_GRID: tuple[int, ...] = (10, 15, 21, 31, 42)
SURVIVAL_STABILITY_FLOOR = 0.80
TIER1_DEPTH = ep_mod.TIER1_DEPTH
TIER2_DEPTH = ep_mod.TIER2_DEPTH
REBOUND_WINDOW = 21
USEFUL_ZONE_W = 15


# ---------------------------------------------------------------------------
# the selection rules, in words, BEFORE any value exists
# ---------------------------------------------------------------------------
RULES: dict[str, str] = {
    "Y": "declared, not partition-computed. 15% — the F2 resets-convention anchor, so "
         "the decline qualification shares its threshold with the drawdown-grammar "
         "feature that counts resets.",
    "X": "median over calibration names of (0.15 * close / ATR14) evaluated at each "
         "name's rolling-126d-high refresh dates, rounded to the nearest 0.5. The "
         "inner quantity is 'how many ATRs is a 15% fall for this name at its high', "
         "so X is the A0 gate that admits the same economic move Y admits.",
    "N": "smallest of {10,15,21,31,42} such that at least 80% of calibration "
         "tier-2-depth candidate lows surviving N sessions also survive 2N — the "
         "label-stability knee. Candidate lows are qualified on DEPTH ONLY, so the "
         "rule that chooses N does not presuppose N.",
    "k": "P25 of the 21-session post-minimum rebound in A0 units over calibration raw "
         "local minima at tier-2 depth, rounded to the nearest 0.5.",
    "z": "the same statistic as k expressed in percent, rounded to the nearest 1%.",
    "M": "declared, not partition-computed. 63 sessions — one quarter for a reclaim to "
         "resolve held/failed.",
    "m": "declared, not partition-computed. 10 sessions for a failed breakdown to "
         "recover the undercut level.",
    "D1": "P25 of candidate tier-1 (depth >= 35%) episode durations, rounded DOWN to "
          "the nearest 5 sessions.",
    "D2": "P25 of candidate tier-2 (depth >= 20%) episode durations, rounded DOWN to "
          "the nearest 5 sessions.",
    "theta_dw": "pooled P85 of |dd| (dd = close/252d-max - 1) over calibration "
                "name-days, rounded to the nearest 5%.",
    "theta_bd": "pooled P75 of |d200| given d200 < 0 over calibration name-days, "
                "rounded to the nearest 1%.",
    "theta_pb": "pooled P50 of |dd| given d200 > 0 over calibration name-days, rounded "
                "to the nearest 1%.",
    "theta_up": "declared, not partition-computed. 0 — structural uptrend begins at the "
                "200DMA, not at an offset nobody could defend.",
    "J": "declared, not partition-computed. 40 percentile points.",
    "V": "declared, not partition-computed. 21 sessions — the band-jump lookback.",
    "E": "declared, not partition-computed. 5 sessions — how long a gap keeps the "
         "dislocation state alive.",
    "R": "declared, not partition-computed. 126 sessions — how long a washout or "
         "breakdown stays 'recent' for the reclaim rule.",
    "g": "pooled P99 of gap_atr over calibration name-days, rounded to the nearest 0.5. "
         "The gap basis is plane-dependent and the pooled statistic mixes both bases; "
         "that asymmetry is recorded on every state row.",
    "w": "declared, not partition-computed. 15 sessions — grain-neutral useful-zone "
         "width, chosen so a weekly-grain instrument is not mechanically excluded.",
    "delta": "P75 of min |price - low| / A0 within the +w window over calibration "
             "tier-2+ durable lows, rounded to the nearest 0.25.",
    "theta_fs": "P75 of the A0-depth of candidate-low violations (the lower low that "
                "killed an N-survival candidate), rounded to the nearest 0.25.",
    "P_pre": "declared, not partition-computed. 5 sessions of pre-leg attribution "
             "window.",
    "S_reclaim": "declared, not partition-computed. 5 consecutive sessions above the "
                 "200DMA make a recapture 'sustained'. Registration §7 says 'sustained' "
                 "without an operational definition; this supplies one rather than "
                 "leaving the reclaim type unbuildable.",
}

DECLARED_CONSTANTS: dict[str, float | int] = {
    "Y": 0.15, "M": 63, "m": 10, "theta_up": 0.0, "J": 40.0, "V": 21, "E": 5, "R": 126,
    "w": USEFUL_ZONE_W, "P_pre": 5, "S_reclaim": 5,
}


# ---------------------------------------------------------------------------
# rounding helpers (each named after the rule text that calls it)
# ---------------------------------------------------------------------------
def _round_nearest(x: float, step: float) -> float:
    return float(round(x / step) * step)


def _round_down_to(x: float, step: int) -> int:
    return int(math.floor(x / step) * step)


# ---------------------------------------------------------------------------
# per-name extraction (worker)
# ---------------------------------------------------------------------------
def extract_one(args: tuple[str, str, str]) -> dict[str, Any] | None:
    """All partition material for one calibration name, sliced at the history cutoff."""
    symbol, plane_id, cutoff = args
    try:
        df = load_symbol(symbol, plane_id, REPO_ROOT)
    except Exception as exc:  # noqa: BLE001
        log.warning("%s: unreadable (%s)", symbol, exc)
        return None
    df = df.loc[df.index <= pd.Timestamp(cutoff)]
    if len(df) < 300:
        return None

    close = df["close"].astype(float)
    cv = close.to_numpy(dtype=float)
    n = len(cv)

    # --- X: 0.15 * close / ATR14 at each 126d-high refresh date ---------
    a0 = ep_mod.a0_series(df).to_numpy(dtype=float)
    refresh = ep_mod.high_refresh_indices(df)
    x_vals = [
        0.15 * cv[i] / a0[i] for i in refresh if np.isfinite(a0[i]) and a0[i] > 0
    ]
    x_stat = float(np.median(x_vals)) if x_vals else np.nan

    # --- candidate lows (DEPTH-ONLY qualification) -----------------------
    cands = ep_mod.candidate_lows(df, min_depth=TIER2_DEPTH)
    rows: list[dict[str, Any]] = []
    for c in cands:
        i = int(c["low_i"])
        a0_low = float(c["a0_low"])
        if not np.isfinite(a0_low) or a0_low <= 0:
            continue
        rec: dict[str, Any] = {
            "low_price": float(c["low_price"]),
            "a0_low": a0_low,
            "depth": float(c["depth"]),
            "duration": int(c["duration"]),
            "leg_i": int(c["leg_i"]),
        }
        for N in N_GRID:
            hi1, hi2 = i + N, i + 2 * N
            rec[f"min_{N}"] = float(cv[i + 1 : hi1 + 1].min()) if hi1 < n else np.nan
            rec[f"max_{N}"] = float(cv[i + 1 : hi1 + 1].max()) if hi1 < n else np.nan
            rec[f"min2_{N}"] = float(cv[i + 1 : hi2 + 1].min()) if hi2 < n else np.nan
        rec["max_21"] = (
            float(cv[i + 1 : i + REBOUND_WINDOW + 1].max())
            if i + REBOUND_WINDOW < n else np.nan
        )
        rec["min_abs_dev_w"] = (
            float(np.abs(cv[i + 1 : i + USEFUL_ZONE_W + 1] - cv[i]).min())
            if i + USEFUL_ZONE_W < n else np.nan
        )
        rows.append(rec)

    # --- pooled name-day state variables ---------------------------------
    sv = state_mod.state_variables(df, plane_id)
    dd = sv["dd"].to_numpy(dtype=float)
    d200 = sv["d200"].to_numpy(dtype=float)
    gap = sv["gap_atr"].to_numpy(dtype=float)
    dd_ok = np.isfinite(dd)
    d2_ok = np.isfinite(d200)

    return {
        "symbol": symbol,
        "x_stat": x_stat,
        "candidates": rows,
        "dd_abs": np.abs(dd[dd_ok]).astype("float32"),
        "d200_neg_abs": np.abs(d200[d2_ok & (d200 < 0)]).astype("float32"),
        "dd_pos_d200": np.abs(dd[dd_ok & d2_ok & (d200 > 0)]).astype("float32"),
        "gap_atr": gap[np.isfinite(gap)].astype("float32"),
        "gap_basis": str(sv["gap_basis"].iloc[0]) if len(sv) else "n/a",
        "n_rows": int(n),
    }


# ---------------------------------------------------------------------------
# aggregation: apply each rule
# ---------------------------------------------------------------------------
def choose_constants(parts: Sequence[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Apply every selection rule to the pooled partition material.

    Returns ``(values, receipts)``. Each receipt names the statistic, its raw value
    before rounding, and the N behind it, so a reader can see what the rounding did.
    """
    values: dict[str, Any] = dict(DECLARED_CONSTANTS)
    receipts: dict[str, Any] = {}

    for name, v in DECLARED_CONSTANTS.items():
        receipts[name] = {
            "value": v, "rule": RULES[name], "declared": True,
            "note": "declared, not partition-computed",
        }

    # ---- X ---------------------------------------------------------------
    x_stats = np.asarray([p["x_stat"] for p in parts if np.isfinite(p["x_stat"])], dtype=float)
    x_raw = float(np.median(x_stats)) if len(x_stats) else float("nan")
    values["X"] = _round_nearest(x_raw, 0.5)
    receipts["X"] = {
        "value": values["X"], "rule": RULES["X"], "declared": False,
        "raw": x_raw, "n_names": int(len(x_stats)),
        "note": "median of per-name medians over 126d-high refresh dates",
    }

    cands = [c for p in parts for c in p["candidates"]]
    t2 = [c for c in cands if c["depth"] >= TIER2_DEPTH]

    # ---- N ---------------------------------------------------------------
    n_table: list[dict[str, Any]] = []
    chosen_N = N_GRID[-1]
    for N in N_GRID:
        surv, surv2 = 0, 0
        for c in t2:
            mn, mn2 = c.get(f"min_{N}"), c.get(f"min2_{N}")
            if not (np.isfinite(mn) and np.isfinite(mn2)):
                continue
            if mn >= c["low_price"]:
                surv += 1
                if mn2 >= c["low_price"]:
                    surv2 += 1
        share = (surv2 / surv) if surv else float("nan")
        n_table.append({"N": N, "n_surviving_N": surv, "share_also_surviving_2N": share})
        if np.isfinite(share) and share >= SURVIVAL_STABILITY_FLOOR and chosen_N == N_GRID[-1]:
            chosen_N = N
    # smallest N clearing the floor; if none clears it, the grid's largest is used and said so
    clears = [r["N"] for r in n_table if np.isfinite(r["share_also_surviving_2N"])
              and r["share_also_surviving_2N"] >= SURVIVAL_STABILITY_FLOOR]
    values["N"] = int(min(clears)) if clears else int(N_GRID[-1])
    receipts["N"] = {
        "value": values["N"], "rule": RULES["N"], "declared": False,
        "grid": n_table, "floor": SURVIVAL_STABILITY_FLOOR,
        "note": ("smallest N clearing the floor" if clears else
                 "NO grid value cleared the 80% floor — the grid's largest N is used and "
                 "this failure is reported rather than the floor being lowered"),
    }
    N = values["N"]

    # ---- k, z -------------------------------------------------------------
    reb_atr, reb_pct = [], []
    for c in t2:
        mx = c.get("max_21")
        if not np.isfinite(mx):
            continue
        reb = mx - c["low_price"]
        reb_atr.append(reb / c["a0_low"])
        reb_pct.append(100.0 * reb / c["low_price"])
    k_raw = float(np.percentile(reb_atr, 25)) if reb_atr else float("nan")
    z_raw = float(np.percentile(reb_pct, 25)) if reb_pct else float("nan")
    values["k"] = _round_nearest(k_raw, 0.5)
    values["z"] = _round_nearest(z_raw, 1.0) / 100.0
    receipts["k"] = {"value": values["k"], "rule": RULES["k"], "declared": False,
                     "raw": k_raw, "n_candidates": len(reb_atr)}
    receipts["z"] = {"value": values["z"], "rule": RULES["z"], "declared": False,
                     "raw_pct": z_raw, "n_candidates": len(reb_pct)}

    # ---- D1, D2 -----------------------------------------------------------
    per_leg: dict[tuple[int, int], dict[str, Any]] = {}
    for p_i, p in enumerate(parts):
        for c in p["candidates"]:
            key = (p_i, c["leg_i"])
            cur = per_leg.get(key)
            if cur is None or c["depth"] > cur["depth"]:
                per_leg[key] = c
    legs = list(per_leg.values())
    d1_src = [c["duration"] for c in legs if c["depth"] >= TIER1_DEPTH]
    d2_src = [c["duration"] for c in legs if c["depth"] >= TIER2_DEPTH]
    d1_raw = float(np.percentile(d1_src, 25)) if d1_src else float("nan")
    d2_raw = float(np.percentile(d2_src, 25)) if d2_src else float("nan")
    values["D1"] = _round_down_to(d1_raw, 5) if np.isfinite(d1_raw) else 0
    values["D2"] = _round_down_to(d2_raw, 5) if np.isfinite(d2_raw) else 0
    receipts["D1"] = {"value": values["D1"], "rule": RULES["D1"], "declared": False,
                      "raw": d1_raw, "n_legs": len(d1_src)}
    receipts["D2"] = {"value": values["D2"], "rule": RULES["D2"], "declared": False,
                      "raw": d2_raw, "n_legs": len(d2_src)}

    # ---- state thresholds --------------------------------------------------
    dd_abs = np.concatenate([p["dd_abs"] for p in parts]) if parts else np.asarray([])
    d200_neg = np.concatenate([p["d200_neg_abs"] for p in parts]) if parts else np.asarray([])
    dd_pos = np.concatenate([p["dd_pos_d200"] for p in parts]) if parts else np.asarray([])
    gap = np.concatenate([p["gap_atr"] for p in parts]) if parts else np.asarray([])

    dw_raw = float(np.percentile(dd_abs, 85)) if len(dd_abs) else float("nan")
    bd_raw = float(np.percentile(d200_neg, 75)) if len(d200_neg) else float("nan")
    pb_raw = float(np.percentile(dd_pos, 50)) if len(dd_pos) else float("nan")
    g_raw = float(np.percentile(gap, 99)) if len(gap) else float("nan")

    values["theta_dw"] = _round_nearest(dw_raw, 0.05)
    values["theta_bd"] = _round_nearest(bd_raw, 0.01)
    values["theta_pb"] = _round_nearest(pb_raw, 0.01)
    values["g"] = _round_nearest(g_raw, 0.5)
    receipts["theta_dw"] = {"value": values["theta_dw"], "rule": RULES["theta_dw"],
                            "declared": False, "raw": dw_raw, "n_name_days": int(len(dd_abs))}
    receipts["theta_bd"] = {"value": values["theta_bd"], "rule": RULES["theta_bd"],
                            "declared": False, "raw": bd_raw, "n_name_days": int(len(d200_neg))}
    receipts["theta_pb"] = {"value": values["theta_pb"], "rule": RULES["theta_pb"],
                            "declared": False, "raw": pb_raw, "n_name_days": int(len(dd_pos))}
    receipts["g"] = {"value": values["g"], "rule": RULES["g"], "declared": False,
                     "raw": g_raw, "n_name_days": int(len(gap)),
                     "gap_bases_pooled": sorted({p["gap_basis"] for p in parts})}

    # ---- delta, theta_fs (need N, k, z) -----------------------------------
    k_v, z_v = values["k"], values["z"]
    devs, violations = [], []
    for c in t2:
        mn, mx = c.get(f"min_{N}"), c.get(f"max_{N}")
        if not np.isfinite(mn):
            continue
        if mn < c["low_price"]:
            violations.append((c["low_price"] - mn) / c["a0_low"])
            continue
        if not np.isfinite(mx):
            continue
        reb = mx - c["low_price"]
        durable = (reb >= k_v * c["a0_low"]) and (reb / c["low_price"] >= z_v)
        if durable and np.isfinite(c.get("min_abs_dev_w", np.nan)):
            devs.append(c["min_abs_dev_w"] / c["a0_low"])
    delta_raw = float(np.percentile(devs, 75)) if devs else float("nan")
    fs_raw = float(np.percentile(violations, 75)) if violations else float("nan")
    values["delta"] = _round_nearest(delta_raw, 0.25)
    values["theta_fs"] = _round_nearest(fs_raw, 0.25)
    receipts["delta"] = {"value": values["delta"], "rule": RULES["delta"], "declared": False,
                         "raw": delta_raw, "n_durable_lows": len(devs)}
    receipts["theta_fs"] = {"value": values["theta_fs"], "rule": RULES["theta_fs"],
                            "declared": False, "raw": fs_raw, "n_violations": len(violations)}
    return values, receipts


# ---------------------------------------------------------------------------
# sensitivity grid (registered BEFORE it runs; diagnostic only)
# ---------------------------------------------------------------------------
SENSITIVITY_KEYS: tuple[str, ...] = ("X", "N", "k", "z", "theta_dw", "g")


def sensitivity_configs(values: dict[str, Any]) -> list[dict[str, Any]]:
    """The declared +/-20% grid — one config per (constant, direction), plus base."""
    out = [{"variant": "base", "constant": None, "direction": None,
            **{k: values[k] for k in SENSITIVITY_KEYS}}]
    for key in SENSITIVITY_KEYS:
        for sign, label in ((1.2, "plus20"), (0.8, "minus20")):
            cfg = {k: values[k] for k in SENSITIVITY_KEYS}
            v = values[key] * sign
            cfg[key] = int(round(v)) if isinstance(values[key], int) else float(v)
            cfg.update({"variant": f"{key}_{label}", "constant": key, "direction": label})
            out.append(cfg)
    return out


def _episode_and_state_summary(
    frames: list[tuple[str, str, pd.DataFrame]], values: dict[str, Any], cfg: dict[str, Any]
) -> dict[str, Any]:
    ec = ep_mod.EpisodeConstants(
        X=float(cfg["X"]), Y=float(values["Y"]), N=int(cfg["N"]), k=float(cfg["k"]),
        z=float(cfg["z"]), M=int(values["M"]), m=int(values["m"]),
        D1=int(values["D1"]), D2=int(values["D2"]), S_reclaim=int(values["S_reclaim"]),
    )
    sc = state_mod.StateConstants(
        g=float(cfg["g"]), theta_dw=float(cfg["theta_dw"]), theta_bd=float(values["theta_bd"]),
        theta_pb=float(values["theta_pb"]), theta_up=float(values["theta_up"]),
        J=float(values["J"]), V=int(values["V"]), E=int(values["E"]), R=int(values["R"]),
    )
    n_ep = 0
    shares: dict[str, float] = {s: 0.0 for s in state_mod.STATES}
    total_days = 0
    for sym, plane, df in frames:
        st = state_mod.tag_states(df, plane, sc)
        cat = ep_mod.build_catalog(
            df, symbol=sym, plane_id=plane, const=ec, states=st["state"]
        )
        n_ep += int(len(cat))
        vc = st["state"].value_counts()
        for s, c in vc.items():
            shares[str(s)] = shares.get(str(s), 0.0) + float(c)
        total_days += int(len(st))
    if total_days:
        shares = {k: v / total_days for k, v in shares.items()}
    return {"n_episodes": n_ep, "state_shares": shares, "n_names": len(frames)}


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
@register_trials(
    TRIAL_FAMILY, budget=1 + 2 * len(SENSITIVITY_KEYS), basis="itemized",
    reason="W1 calibration sensitivity grid (+/-20% on X,N,k,z,theta_dw,g) — "
           "exploratory/diagnostic; never used to re-pick a constant",
)
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--sensitivity-names", type=int, default=40)
    ap.add_argument("--skip-sensitivity", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    # ---- draw-order gate -------------------------------------------------
    if not MANIFEST_PATH.exists():
        raise SystemExit(
            f"REFUSING to calibrate: no partition manifest at {MANIFEST_PATH}. Constants "
            "may only be set AFTER the blind arm and the sealed calibration partition are "
            "drawn and hashed (registration §3/§4). Run "
            "scripts/stock_identity_build_atlas.py --stage partition first."
        )
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    cal = manifest["calibration_partition"]
    members = list(cal["members"])
    pilot = set(manifest["pilot"]["members"])
    blind = set(manifest["blind_arm"]["members"])
    cutoff = cal["calibration_history_cutoff"]
    planes = manifest["universe"]["plane_by_symbol"]

    # A drawn member that is ALSO pilot or blind means the draw itself is broken — that
    # is a partition violation and there is nothing to do but stop.
    contaminated = [s for s in members if s in pilot or s in blind]
    if contaminated:
        raise SystemExit(
            f"REFUSING to calibrate: {len(contaminated)} drawn name(s) are also pilot or "
            f"blind members ({contaminated[:10]}). Pilot and blind names contribute nothing "
            "to constant-setting under any clause (§16.2), so the draw is invalid."
        )
    # A hygiene-blocked member is different: the DRAW is valid (the universe keeps
    # hygiene-flagged names — censored-never-dropped), but the name must not be READ.
    # Skipping it here rather than re-drawing keeps calibration_sha256 a pure function of
    # (snapshot, seed); silently re-drawing would make the seal unreproducible.
    skipped = [s for s in members if s in COMPUTE_BLOCKLIST]
    eligible = [s for s in members if s not in COMPUTE_BLOCKLIST]
    for s in skipped:
        print(f"[gate] SKIPPING drawn member {s}: {COMPUTE_BLOCKLIST[s]}", flush=True)
    print(
        f"[gate] manifest ok · partition={cal['name']} · n_drawn={len(members)} · "
        f"n_readable={len(eligible)} · skipped_on_hygiene={skipped or 'none'} · "
        f"history cutoff={cutoff} (asof - 126td) · calibration_sha256="
        f"{cal['calibration_sha256'][:16]}…",
        flush=True,
    )

    # ---- pass A: partition material -------------------------------------
    tasks = [(s, planes[s], cutoff) for s in eligible if s in planes]
    with mp.Pool(processes=max(1, args.workers)) as pool:
        parts = [p for p in pool.imap_unordered(extract_one, tasks, chunksize=8) if p]
    print(f"[extract] {len(parts)}/{len(tasks)} calibration names produced material", flush=True)
    if not parts:
        raise SystemExit("no calibration material extracted — refusing to freeze constants")

    # Gate 3, the read-side half: every symbol whose data reached this aggregation must
    # be a drawn, hygiene-eligible calibration member and nothing else.
    read_syms = {p["symbol"] for p in parts}
    stray = read_syms - set(eligible)
    if stray:
        raise SystemExit(
            f"REFUSING to freeze constants: read {len(stray)} symbol(s) outside the sealed "
            f"partition ({sorted(stray)[:10]})"
        )

    # ---- apply the rules --------------------------------------------------
    values, receipts = choose_constants(parts)

    print("\n=== W1 constants (SI-SEALED-CAL-P1) ===", flush=True)
    for key in sorted(receipts):
        r = receipts[key]
        tag = "declared" if r.get("declared") else "partition-computed"
        raw = r.get("raw", r.get("raw_pct"))
        raw_s = f" raw={raw:.4f}" if isinstance(raw, float) and np.isfinite(raw) else ""
        print(f"  {key:<10} = {r['value']!r:<10} [{tag}]{raw_s}", flush=True)

    # ---- sensitivity (registered above, diagnostic only) ------------------
    configs = sensitivity_configs(values)
    ledger = TrialLedger(family=TRIAL_FAMILY)
    n_new = ledger.log_grid(configs, family=TRIAL_FAMILY, info_cutoff=str(cutoff),
                            source="stock_identity_w1_sensitivity_grid",
                            note="diagnostic-only; never used to re-pick a constant")
    reg_hash = None
    try:
        import hashlib as _h
        reg_hash = _h.sha256(
            json.dumps(configs, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
    except Exception:  # noqa: BLE001
        pass
    print(
        f"\n[trial-ledger] family={TRIAL_FAMILY} configs={len(configs)} newly-distinct={n_new} "
        f"effective_n={ledger.effective_n(TRIAL_FAMILY)} grid_sha256={reg_hash}",
        flush=True,
    )

    sensitivity: list[dict[str, Any]] = []
    if not args.skip_sensitivity:
        rng = np.random.default_rng(20260814)
        pick = sorted(rng.permutation(len(eligible))[: args.sensitivity_names])
        sample = [eligible[i] for i in pick if eligible[i] in planes]
        frames = []
        for s in sample:
            try:
                d = load_symbol(s, planes[s], REPO_ROOT)
            except Exception:  # noqa: BLE001
                continue
            d = d.loc[d.index <= pd.Timestamp(cutoff)]
            if len(d) >= 300:
                frames.append((s, planes[s], d))
        base = None
        for cfg in configs:
            summ = _episode_and_state_summary(frames, values, cfg)
            if cfg["variant"] == "base":
                base = summ
            row = {"variant": cfg["variant"], "constant": cfg["constant"],
                   "n_episodes": summ["n_episodes"], "n_names": summ["n_names"]}
            if base:
                row["episode_delta_vs_base"] = summ["n_episodes"] - base["n_episodes"]
                row["max_state_share_delta"] = max(
                    abs(summ["state_shares"].get(s, 0.0) - base["state_shares"].get(s, 0.0))
                    for s in state_mod.STATES
                )
            sensitivity.append(row)
        print("\n=== sensitivity (diagnostic; never re-picks a value) ===", flush=True)
        for row in sensitivity:
            print(
                f"  {row['variant']:<18} episodes={row['n_episodes']:<6} "
                f"delta={row.get('episode_delta_vs_base', 0):<6} "
                f"max_state_share_delta={row.get('max_state_share_delta', 0.0):.4f}",
                flush=True,
            )

    # ---- write ------------------------------------------------------------
    spec_obj = fp_spec()
    # The constants' OWN spec hash covers the frozen decisions (version, values, rule
    # text) and deliberately NOT the receipts, whose sample counts would change the
    # hash on any re-read of the same sealed partition without any constant moving.
    constants_spec = {
        "version": "v1",
        "partition_name": cal["name"],
        "values": values,
        "rules": RULES,
    }
    si_constants_spec_hash = __import__("hashlib").sha256(
        json.dumps(constants_spec, sort_keys=True, separators=(",", ":"),
                   default=str).encode("utf-8")
    ).hexdigest()
    payload = {
        "si_constants_spec_hash": si_constants_spec_hash,
        "schema": "stock_identity.constants.v1",
        "version": "v1",
        "partition_name": cal["name"],
        "asof": manifest["asof"],
        "calibration_history_cutoff": cutoff,
        "calibration_material": (
            "component (i) of §4 only — the drawn names' own history. The permitted "
            "pre-boundary history of undrawn pool names was NOT consumed; using less "
            "than the permitted material is strictly conservative and is recorded here."
        ),
        "n_calibration_names_drawn": len(members),
        "n_calibration_names_read": len(parts),
        "skipped_on_hygiene": {s: COMPUTE_BLOCKLIST[s] for s in skipped},
        "values": values,
        "rules": RULES,
        "receipts": receipts,
        "sensitivity_grid": {
            "keys": list(SENSITIVITY_KEYS),
            "perturbation": "+/-20%",
            "status": "registered in the Trial Ledger BEFORE running; diagnostic only",
            "trial_family": TRIAL_FAMILY,
            "trial_grid_sha256": reg_hash,
            "trial_effective_n": int(ledger.effective_n(TRIAL_FAMILY)),
            "results": sensitivity,
        },
        "partition_procedure_sha256": manifest["partition_procedure_sha256"],
        "calibration_sha256": cal["calibration_sha256"],
        "blind_sha256": manifest["blind_arm"]["blind_sha256"],
        "universe_sha256": manifest["universe"]["universe_sha256"],
        "fingerprint_spec_hash": fp_spec_hash(spec_obj),
        "state_slope_lookback_sessions": state_mod.SLOPE_LOOKBACK,
        "tier_depth_floors": {"tier1": TIER1_DEPTH, "tier2": TIER2_DEPTH},
        "sealing": (
            "SI-SEALED-CAL-P1 sets/freezes this constant family exactly once and is "
            "thereafter excluded from confirmatory grading. Constants never change after "
            "sealing; a revision voids the affected preregs."
        ),
        "authority": authority_block(),
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
                        encoding="utf-8")
    print(f"\n[hash] si_constants_spec_hash={si_constants_spec_hash}", flush=True)
    print(f"[write] {OUT_PATH}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
