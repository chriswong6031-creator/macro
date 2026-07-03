"""COILED-CA — durable-bottom detector on Canada · Phase-0 harness.

A REAL FORK of research/entry_timing/wave3.py's close-only path (the CN/HK COILED
replication). It reuses the wave3/wave2/wave1 leak-free primitives VERBATIM (labels,
outcomes, cohort fraction, COILED/STAR assignment, next-bar fills, table builders) and
adds ONLY: a Canada names-panel loader, a deep TSX sector-ETF context panel, and the
pre-registered G-CA gate (name-clustered bootstrap = the DSR analog).

Pre-registration: research/COILED_CA_PREREG.md (committed BEFORE this code).
Gate (CN wave-3 verbatim): Δclean15 ≥ +3pp, Δstop5 ≤ +1pp, n_COILED ≥ 400, split-half
sign-stable (cut 2024-01-01), per-name majority ≥ 55%, name-clustered bootstrap 90% LB > 0.
Robustness: sign at clean10/clean20, dead-money lower. NO WIRING.

Run:
  .venv/bin/python -m research.entry_timing.wave3_ca --workers 6
Writes reports/coiled-ca-phase0.md + research/entry_timing/wave3_ca_out/*. No commit,
no site build, NO engine wiring.
"""
from __future__ import annotations

import sys
import time
import json
import argparse
import warnings
import logging
from pathlib import Path
from multiprocessing import Pool

import numpy as np
import pandas as pd

if __name__ == "__main__":
    warnings.filterwarnings("ignore")
    logging.disable(logging.CRITICAL)

ROOT = Path(__file__).resolve().parents[2]
SIG_ENG = ROOT / "research" / "signal_engine"
ENTRY_TIMING = ROOT / "research" / "entry_timing"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SIG_ENG))
sys.path.insert(0, str(ENTRY_TIMING))

import tuning_harness as TH  # noqa: E402
import wave1                  # noqa: E402
import wave2                  # noqa: E402
import wave3                  # noqa: E402  (fork base — reuse its close-only functions)

from wave1 import H6_COHORT_THRESH  # noqa: E402
from wave3 import (               # noqa: E402
    load_close_only_wide,
    build_sector_d_matrix_from_close_dict,
    build_T1_w3, build_T3_w3, build_T4_w3,
    _closeonly_worker,
)
from wave2 import _serialize_d_matrix, _rate_row  # noqa: E402
from engine.trial_ledger import TrialLedger, register_trials  # noqa: E402

# ── CA panel constants (pre-registered) ───────────────────────────────────────
CA_CLOSES   = ROOT / "data" / "canada_search" / "closes.parquet"
CA_MEMBERS  = ROOT / "data" / "canada_search" / "members.parquet"
CA_MIN_BARS = 800
CA_EVAL_START = pd.Timestamp("2022-09-01")   # washout_ctx 308-bar + 126 fwd warmup
CA_HALF_CUT   = pd.Timestamp("2024-01-01")   # mechanical near-midpoint (pre-registered)
VARIANTS_CLOSE = ["m2d_s3d", "base3d"]

# Deep TSX sector-ETF context panel (§1.2 — DIFFERENT cohort mechanic, context only)
CA_ETF_DIR = ROOT / "data" / "canada"
CA_ETFS = ["XEG", "XGD", "XFN", "XIT", "XRE", "XMA", "XBM", "XUT", "XST"]

# DSR/multiple-testing family budget (masterplan program budget ≈40)
PROGRAM_N_TRIALS = 40
FAMILY = "coiled_ca_phase0"

# Gate thresholds (CN wave-3 verbatim — fixed in the pre-reg, no CA loosening)
G_LIFT_MIN   = 3.0     # Δclean15 ≥ +3pp
G_STOP_MAX   = 1.0     # Δstop5 ≤ +1pp
G_N_MIN      = 400     # n_COILED
G_PERNAME    = 55.0    # % COILED-wins ≥ 55
BOOT_B       = 5000
BOOT_SEED    = 17
BOOT_LEVEL   = 0.90    # one-sided lower bound level (DSR≥0.90 analog)


# ══════════════════════════════════════════════════════════════════════════════
# CA names-panel run (reuses wave3's close-only per-name worker verbatim)
# ══════════════════════════════════════════════════════════════════════════════
def run_ca_names(workers: int, out_dir: Path) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    print(f"COILED-CA names | eval_start={CA_EVAL_START.date()} half_cut={CA_HALF_CUT.date()} "
          f"| min_bars={CA_MIN_BARS} | workers={workers}")
    close_dict = load_close_only_wide(CA_CLOSES, CA_MIN_BARS)
    print(f"Names with >={CA_MIN_BARS} bars: {len(close_dict)}")

    sector_map: dict[str, str] = {}
    mem = pd.read_parquet(CA_MEMBERS)
    if "sector" in mem.columns:
        for sym in mem.index:
            sector_map[sym] = mem.loc[sym, "sector"]
    print(f"Sector map: {len(sector_map)} tickers, "
          f"{len(set(sector_map.values()))} sectors")

    print("Building sector weekly-D matrix (cohort peers)...")
    t0 = time.time()
    sector_d_matrix = build_sector_d_matrix_from_close_dict(close_dict, sector_map)
    print(f"  sector-D matrix: {len(sector_d_matrix)} tickers ({time.time()-t0:.1f}s)")
    sector_d_matrix_ser = _serialize_d_matrix(sector_d_matrix)

    worker_args = []
    for ticker, daily in close_dict.items():
        worker_args.append((
            ticker,
            daily.to_numpy().tolist(),
            daily.index.strftime("%Y-%m-%d").tolist(),
            sector_map,
            sector_d_matrix_ser,
            None,   # theme_peers — no CA theme cohort in this battery (pre-stated)
            None,   # theme_d_matrix
            CA_EVAL_START.strftime("%Y-%m-%d"),
            CA_MIN_BARS,
            VARIANTS_CLOSE,
        ))

    print(f"\nProcessing {len(worker_args)} names with {workers} workers...")
    t0 = time.time()
    if workers <= 1:
        results = [_closeonly_worker(a) for a in worker_args]
    else:
        with Pool(workers) as pool:
            results = pool.map(_closeonly_worker, worker_args)

    all_fires = {v: [] for v in VARIANTS_CLOSE}
    all_events: list[dict] = []
    processed: list[str] = []
    errors: list[str] = []
    for ticker, result in results:
        if "_error" in result:
            errors.append(f"{ticker}: {result['_error']}")
            continue
        if not result:
            continue
        for v in VARIANTS_CLOSE:
            all_fires[v].extend(result.get(v, []))
        all_events.extend(result.get("events", []))
        processed.append(ticker)
    elapsed = time.time() - t0
    if errors:
        print(f"Errors ({len(errors)}): {errors[:5]}")
    print(f"Done: {len(processed)} names in {elapsed:.1f}s")

    events_df = pd.DataFrame(all_events)
    if "t0" in events_df.columns:
        events_df["t0"] = pd.to_datetime(events_df["t0"])
    fires_dfs = {}
    for v in VARIANTS_CLOSE:
        rows = all_fires[v]
        if rows:
            df = pd.DataFrame(rows)
            df["sig_date"] = pd.to_datetime(df["sig_date"])
            df["fill_date"] = pd.to_datetime(df["fill_date"])
            fires_dfs[v] = df
        else:
            fires_dfs[v] = pd.DataFrame()

    out_dir.mkdir(parents=True, exist_ok=True)
    events_df.to_parquet(out_dir / "events.parquet", index=False)
    for v in VARIANTS_CLOSE:
        fires_dfs[v].to_parquet(out_dir / f"fires_{v}.parquet", index=False)

    meta = {"n_names_processed": len(processed), "n_names_ge_minbars": len(close_dict),
            "eval_start": str(CA_EVAL_START.date()), "half_cut": str(CA_HALF_CUT.date()),
            "min_bars": CA_MIN_BARS, "errors": errors}
    return meta, events_df, fires_dfs


# ══════════════════════════════════════════════════════════════════════════════
# Stratum masks + name-clustered bootstrap (the DSR analog, §3 gate 6)
# ══════════════════════════════════════════════════════════════════════════════
def _masks(fires: pd.DataFrame):
    washout = fires["in_washout_ctx"].astype(bool) if "in_washout_ctx" in fires else pd.Series(False, index=fires.index)
    coiled  = fires["coiled"].astype(bool) if "coiled" in fires else pd.Series(False, index=fires.index)
    star    = fires["star"].astype(bool) if "star" in fires else pd.Series(False, index=fires.index)
    h6 = fires["h6_cohort_sector"] if "h6_cohort_sector" in fires else pd.Series(np.nan, index=fires.index)
    ncw = washout & h6.notna() & (h6 < H6_COHORT_THRESH)
    return coiled, ncw, star, washout


def _rate(sub: pd.DataFrame, col: str) -> float:
    if len(sub) == 0 or col not in sub.columns:
        return float("nan")
    v = sub[col].dropna()
    return round(float(v.mean()) * 100, 2) if len(v) else float("nan")


def name_clustered_boot(fires: pd.DataFrame, coiled_mask, ncw_mask,
                        col: str = "clean15", B: int = BOOT_B, seed: int = BOOT_SEED) -> dict:
    """Name-clustered block bootstrap of Δ = rate(COILED) − rate(NCW) on `col`.

    Resampling UNIT = the NAME (independent-episode effective-N), not the overlapping fire.
    Returns the 5/50/95 percentiles of Δ (pp) and the one-sided 90% lower bound.
    """
    c = fires[coiled_mask].copy()
    n = fires[ncw_mask].copy()
    if len(c) == 0 or len(n) == 0:
        return {}
    names = sorted(set(fires["ticker"].unique()))
    # pre-group per-name fire indices for the two strata
    c_by = {t: c[c["ticker"] == t][col].dropna().to_numpy() for t in names}
    n_by = {t: n[n["ticker"] == t][col].dropna().to_numpy() for t in names}
    names = [t for t in names if len(c_by[t]) or len(n_by[t])]
    rng = np.random.default_rng(seed)
    m = len(names)
    deltas = np.empty(B)
    for k in range(B):
        pick = rng.integers(0, m, m)
        cv, nv = [], []
        for j in pick:
            t = names[j]
            if len(c_by[t]):
                cv.append(c_by[t])
            if len(n_by[t]):
                nv.append(n_by[t])
        if not cv or not nv:
            deltas[k] = np.nan
            continue
        cc = np.concatenate(cv); nn = np.concatenate(nv)
        deltas[k] = (cc.mean() - nn.mean()) * 100
    deltas = deltas[~np.isnan(deltas)]
    if len(deltas) < B * 0.5:
        return {}
    lb90 = float(np.percentile(deltas, 100 * (1 - BOOT_LEVEL)))  # one-sided 90% LB
    return {
        "delta_pp_p5": round(float(np.percentile(deltas, 5)), 2),
        "delta_pp_med": round(float(np.percentile(deltas, 50)), 2),
        "delta_pp_p95": round(float(np.percentile(deltas, 95)), 2),
        "lb90_one_sided": round(lb90, 2),
        "lb90_gt0": bool(lb90 > 0),
        "prob_gt0": round(float(np.mean(deltas > 0)), 3),
        "n_names": m, "B": len(deltas),
    }


def naive_two_sample(fires, coiled_mask, ncw_mask, col="clean15"):
    """Naive (fire-level, unclustered) Δ point estimate — shown so the clustering haircut
    is visible next to it."""
    c = fires[coiled_mask][col].dropna().to_numpy()
    n = fires[ncw_mask][col].dropna().to_numpy()
    if len(c) == 0 or len(n) == 0:
        return {}
    return {"delta_pp": round((c.mean() - n.mean()) * 100, 2),
            "n_coiled": int(len(c)), "n_ncw": int(len(n))}


# ══════════════════════════════════════════════════════════════════════════════
# Deep TSX sector-ETF context panel (§1.2 — cross-ETF cohort, DIFFERENT mechanism)
# ══════════════════════════════════════════════════════════════════════════════
def run_deep_etfs() -> dict:
    """Context-only: treat the 9 sector ETFs as ONE cross-ETF cohort. For each ETF fire,
    cohort = fraction of the OTHER ETFs whose weekly-D < 30 on that date. COILED = washout
    × cross-ETF cohort ≥ 0.40. Reported qualitatively; DOES NOT feed the verdict."""
    cols, incep = {}, {}
    for e in CA_ETFS:
        p = CA_ETF_DIR / f"{e}.TO.parquet"
        if p.exists():
            s = pd.read_parquet(p)["close"].dropna()
            cols[e] = s
            incep[e] = s.first_valid_index()
    if len(cols) < 3:
        return {"error": "insufficient ETFs"}
    close_dict = {e: s for e, s in cols.items()}
    # single "sector" per ETF but we want a CROSS-ETF cohort → assign all to one bucket
    sector_map = {e: "TSX_SECTORS" for e in close_dict}
    sector_d_matrix = build_sector_d_matrix_from_close_dict(close_dict, sector_map)
    sector_d_ser = _serialize_d_matrix(sector_d_matrix)

    rows = []
    events_all = []
    for e, daily in close_dict.items():
        if len(daily) < CA_MIN_BARS:
            continue
        args = (e, daily.to_numpy().tolist(), daily.index.strftime("%Y-%m-%d").tolist(),
                sector_map, sector_d_ser, None, None,
                pd.Timestamp("2002-01-01").strftime("%Y-%m-%d"), CA_MIN_BARS, ["m2d_s3d"])
        _, res = _closeonly_worker(args)
        if "_error" in res or not res:
            continue
        rows.extend(res.get("m2d_s3d", []))
        events_all.extend(res.get("events", []))
    if not rows:
        return {"error": "no fires"}
    f = pd.DataFrame(rows)
    coiled, ncw, star, washout = _masks(f)
    out = {
        "n_fires": int(len(f)),
        "inception": {k: (v.date().isoformat() if v is not None else "?") for k, v in incep.items()},
        "ALL":    {"n": int(len(f)), "clean15": _rate(f, "clean15"), "stop5": _rate(f, "stop5")},
        "COILED": {"n": int(coiled.sum()), "clean15": _rate(f[coiled], "clean15"), "stop5": _rate(f[coiled], "stop5")},
        "NCW":    {"n": int(ncw.sum()), "clean15": _rate(f[ncw], "clean15"), "stop5": _rate(f[ncw], "stop5")},
    }
    if out["COILED"]["clean15"] == out["COILED"]["clean15"] and out["NCW"]["clean15"] == out["NCW"]["clean15"]:
        out["delta_clean15_pp"] = round(out["COILED"]["clean15"] - out["NCW"]["clean15"], 2)
    return out


# ══════════════════════════════════════════════════════════════════════════════
# Gate application + verdict
# ══════════════════════════════════════════════════════════════════════════════
def apply_gate(fires_m: pd.DataFrame) -> dict:
    coiled, ncw, star, washout = _masks(fires_m)
    n_coiled = int(coiled.sum())
    n_ncw = int(ncw.sum())

    c15_coiled = _rate(fires_m[coiled], "clean15")
    c15_ncw    = _rate(fires_m[ncw], "clean15")
    s5_coiled  = _rate(fires_m[coiled], "stop5")
    s5_ncw     = _rate(fires_m[ncw], "stop5")
    dm_coiled  = _rate(fires_m[coiled], "dead_money")
    dm_ncw     = _rate(fires_m[ncw], "dead_money")
    c15_star   = _rate(fires_m[star], "clean15")

    d_c15 = round(c15_coiled - c15_ncw, 2) if (c15_coiled == c15_coiled and c15_ncw == c15_ncw) else float("nan")
    d_s5  = round(s5_coiled - s5_ncw, 2) if (s5_coiled == s5_coiled and s5_ncw == s5_ncw) else float("nan")

    # split-half (cut 2024-01-01)
    pre  = fires_m["fill_date"] < CA_HALF_CUT
    post = fires_m["fill_date"] >= CA_HALF_CUT
    def _half_delta(mask):
        cc = _rate(fires_m[mask & coiled], "clean15")
        nn = _rate(fires_m[mask & ncw], "clean15")
        n_c = int((mask & coiled).sum()); n_n = int((mask & ncw).sum())
        d = round(cc - nn, 2) if (cc == cc and nn == nn) else float("nan")
        return {"coiled_clean15": cc, "ncw_clean15": nn, "delta": d, "n_coiled": n_c, "n_ncw": n_n}
    h1 = _half_delta(pre); h2 = _half_delta(post)
    split_stable = (h1["delta"] == h1["delta"] and h2["delta"] == h2["delta"]
                    and h1["delta"] > 0 and h2["delta"] > 0)

    # per-name majority (reuse wave3 T4)
    t4 = build_T4_w3(fires_m)
    pername = t4.get("coiled_vs_ncw", {})
    pername_pct = pername.get("pct_coiled_wins_clean15", float("nan"))
    pername_n = pername.get("n_names_qualifying", 0)

    # name-clustered bootstrap (DSR analog)
    boot = name_clustered_boot(fires_m, coiled, ncw, col="clean15")
    naive = naive_two_sample(fires_m, coiled, ncw, col="clean15")

    # robustness: clean10 / clean20 sign + dead-money
    def _delta(col):
        cc = _rate(fires_m[coiled], col); nn = _rate(fires_m[ncw], col)
        return round(cc - nn, 2) if (cc == cc and nn == nn) else float("nan")
    d_c10 = _delta("clean10") if "clean10" in fires_m.columns else float("nan")
    d_c20 = _delta("clean20") if "clean20" in fires_m.columns else float("nan")
    dm_lower = (dm_coiled == dm_coiled and dm_ncw == dm_ncw and dm_coiled < dm_ncw)

    # gate booleans
    g1 = (d_c15 == d_c15 and d_c15 >= G_LIFT_MIN)
    g2 = (d_s5 == d_s5 and d_s5 <= G_STOP_MAX)
    g3 = (n_coiled >= G_N_MIN)
    g4 = split_stable
    g5 = (pername_pct == pername_pct and pername_pct >= G_PERNAME)
    g6 = bool(boot.get("lb90_gt0", False))
    rob_sign = ((d_c10 != d_c10 or d_c10 > 0) and (d_c20 != d_c20 or d_c20 > 0))
    robustness = rob_sign and dm_lower

    all_gates = g1 and g2 and g3 and g4 and g5 and g6

    # verdict mapping (constitution wording)
    if not g3:
        verdict = "INCONCLUSIVE"
    elif d_c15 == d_c15 and d_c15 < 0:
        verdict = "KILL"           # powered wrong-sign (the HK outcome)
    elif all_gates and robustness:
        verdict = "GO"
    elif g1 and g2 and g4 and g5 and (not g6 or not robustness):
        verdict = "ACCRUE"         # right-signed, gates 1-5 hold, sig/robustness short
    else:
        verdict = "NO-GO"

    reasons = []
    if not g1: reasons.append(f"Δclean15 {d_c15} < {G_LIFT_MIN}pp")
    if not g2: reasons.append(f"Δstop5 {d_s5} > {G_STOP_MAX}pp (COILED worse)")
    if not g3: reasons.append(f"n_COILED {n_coiled} < {G_N_MIN}")
    if not g4: reasons.append(f"split-half not both>0 (h1 {h1['delta']} / h2 {h2['delta']})")
    if not g5: reasons.append(f"per-name {pername_pct}% < {G_PERNAME}% (n={pername_n})")
    if not g6: reasons.append(f"bootstrap 90% LB {boot.get('lb90_one_sided')} ≤ 0")
    if not robustness: reasons.append(f"robustness: clean10 Δ {d_c10}, clean20 Δ {d_c20}, dm_lower={dm_lower}")
    if all_gates and robustness:
        reasons = ["all 6 gates + robustness pass"]

    return {
        "verdict": verdict, "reasons": reasons,
        "n_coiled": n_coiled, "n_ncw": n_ncw,
        "clean15": {"coiled": c15_coiled, "ncw": c15_ncw, "star": c15_star, "delta": d_c15},
        "stop5": {"coiled": s5_coiled, "ncw": s5_ncw, "delta": d_s5},
        "dead_money": {"coiled": dm_coiled, "ncw": dm_ncw, "lower": dm_lower},
        "split_half": {"h1_pre_2024": h1, "h2_post_2024": h2, "stable": split_stable},
        "per_name": {"pct": pername_pct, "n_qualifying": pername_n},
        "bootstrap": boot, "naive": naive,
        "robustness": {"clean10_delta": d_c10, "clean20_delta": d_c20, "dm_lower": dm_lower, "pass": robustness},
        "gates": {"g1_lift": g1, "g2_stop": g2, "g3_count": g3, "g4_split": g4,
                  "g5_pername": g5, "g6_boot": g6, "robustness": robustness},
    }


# ══════════════════════════════════════════════════════════════════════════════
def _fmt(x):
    return "—" if (x is None or (isinstance(x, float) and x != x)) else x


def render(meta, events_df, fires_dfs, gate, etf) -> str:
    fires_m = fires_dfs["m2d_s3d"]
    n_ev = len(events_df)
    n_dur = int((events_df["label"] == "durable").sum()) if n_ev else 0
    n_trap = int((events_df["label"] == "trap").sum()) if n_ev else 0
    v = gate["verdict"]
    L = ["# COILED-CA — Durable-Bottom Detector on Canada · Phase-0", ""]

    # headline verdict
    cons = {
        "GO":   "PASS. The COILED cohort-washout detector ports to Canada — wire the COILED ranking bonus into the CA board exactly as CN's (follow-up PR, not this one).",
        "KILL": "FAIL (powered wrong-sign). COILED is anti-predictive on Canada with adequate power — CA joins HK on the do-not-port list, with its own evidence.",
        "NO-GO":"COILED does not clear the pre-registered CN wave-3 bar on Canada. Do not wire; the engine does not port to CA on this evidence.",
        "ACCRUE":"COILED shows a right-signed sub-threshold edge on Canada — worth forward-grading, not wiring now.",
        "INCONCLUSIVE":"Too few COILED fires to decide.",
    }[v]
    L += [f"**Verdict: {v}. {cons}**", "",
          f"Battery COILED-CA of the HK/Canada program. `engine/coiled.py` is validated on "
          f"US + CN and refuted on HK; **Canada was never tested until now**. This replicates "
          f"the EXACT CN wave-3 gate (`m2d_s3d` trigger, COILED vs noncoiled_washout clean15 "
          f"spread, split-half, per-name majority, name-clustered bootstrap) on the CA panel. "
          f"Pre-registration: `research/COILED_CA_PREREG.md` (committed before this run; "
          f"thresholds are the CN values verbatim). **Nothing is wired in this PR** (collision "
          f"pact §8.1: china_alpha owns `engine/coiled.py`).", ""]

    # panel
    L += ["## Panel & power (honest)", "",
          f"- **Names panel:** `data/canada_search/closes.parquet` — {meta['n_names_ge_minbars']} of "
          f"219 names clear the {meta['min_bars']}-bar floor ({meta['n_names_processed']} processed). "
          f"Close-only → H4 volume + `low_stop5` skipped (same as CN/HK). "
          f"EVAL_START {meta['eval_start']} (washout_ctx 308-bar + 126-fwd warmup); usable span "
          f"≈ 2.8y, **one macro cycle**.",
          f"- **Events:** {n_ev} total ({n_dur} durable / {n_trap} trap).",
          f"- **`m2d_s3d` fires (eval):** {len(fires_m)}; **COILED {gate['n_coiled']}** / "
          f"noncoiled_washout {gate['n_ncw']}. Power floor n_COILED≥{G_N_MIN}: "
          f"{'MET' if gate['n_coiled']>=G_N_MIN else 'NOT MET'}.",
          f"- **~7× thinner than CN** (10,784 COILED) and single-regime — the split-half is a "
          f"within-cycle split, not a cross-regime replication. Stated on every number.", ""]

    # gate table
    g = gate["gates"]
    L += ["## Pre-registered G-CA gate (CN wave-3 thresholds, verbatim)", "",
          "| # | gate | threshold | observed | pass |",
          "|---|---|---|--:|:--:|",
          f"| 1 | Δclean15 lift | ≥ +{G_LIFT_MIN}pp | {_fmt(gate['clean15']['delta'])}pp | {'✅' if g['g1_lift'] else '❌'} |",
          f"| 2 | Δstop5 (COILED not worse) | ≤ +{G_STOP_MAX}pp | {_fmt(gate['stop5']['delta'])}pp | {'✅' if g['g2_stop'] else '❌'} |",
          f"| 3 | n_COILED | ≥ {G_N_MIN} | {gate['n_coiled']} | {'✅' if g['g3_count'] else '❌'} |",
          f"| 4 | split-half both halves > 0 | both | h1 {_fmt(gate['split_half']['h1_pre_2024']['delta'])} / h2 {_fmt(gate['split_half']['h2_post_2024']['delta'])} | {'✅' if g['g4_split'] else '❌'} |",
          f"| 5 | per-name majority | ≥ {G_PERNAME}% | {_fmt(gate['per_name']['pct'])}% (n={gate['per_name']['n_qualifying']}) | {'✅' if g['g5_pername'] else '❌'} |",
          f"| 6 | name-clustered bootstrap 90% LB | > 0 | {_fmt(gate['bootstrap'].get('lb90_one_sided'))}pp | {'✅' if g['g6_boot'] else '❌'} |",
          f"| R | robustness (clean10/20 sign + dead-money lower) | all | c10 {_fmt(gate['robustness']['clean10_delta'])} · c20 {_fmt(gate['robustness']['clean20_delta'])} · dm_lower {gate['robustness']['dm_lower']} | {'✅' if g['robustness'] else '❌'} |",
          "",
          f"**Gate reasons:** {'; '.join(gate['reasons'])}.", ""]

    # strata detail
    c = gate["clean15"]; s = gate["stop5"]; dm = gate["dead_money"]
    L += ["## Strata (m2d_s3d, next-bar fill)", "",
          "| stratum | n | clean15 | stop5 | dead_money |",
          "|---|--:|--:|--:|--:|",
          f"| COILED | {gate['n_coiled']} | {_fmt(c['coiled'])}% | {_fmt(s['coiled'])}% | {_fmt(dm['coiled'])}% |",
          f"| noncoiled_washout | {gate['n_ncw']} | {_fmt(c['ncw'])}% | {_fmt(s['ncw'])}% | {_fmt(dm['ncw'])}% |",
          f"| STAR (COILED∩div) | — | {_fmt(c['star'])}% | — | — |",
          f"| **Δ (COILED − NCW)** | | **{_fmt(c['delta'])}pp** | **{_fmt(s['delta'])}pp** | |",
          "",
          f"Name-clustered bootstrap (unit = name, B={gate['bootstrap'].get('B','—')}, "
          f"seed {BOOT_SEED}): Δclean15 median {_fmt(gate['bootstrap'].get('delta_pp_med'))}pp, "
          f"5th pct {_fmt(gate['bootstrap'].get('delta_pp_p5'))}pp, "
          f"one-sided 90% LB **{_fmt(gate['bootstrap'].get('lb90_one_sided'))}pp**, "
          f"P(Δ>0) {_fmt(gate['bootstrap'].get('prob_gt0'))}. "
          f"Naive (unclustered, fire-level) Δ {_fmt(gate['naive'].get('delta_pp'))}pp — the gap "
          f"between naive and clustered is the correlated-fire haircut.", ""]

    # split-half
    h1 = gate["split_half"]["h1_pre_2024"]; h2 = gate["split_half"]["h2_post_2024"]
    L += ["## Split-half (cut 2024-01-01, pre-registered)", "",
          "| half | n_COILED | n_NCW | COILED clean15 | NCW clean15 | Δ |",
          "|---|--:|--:|--:|--:|--:|",
          f"| pre-2024 | {h1['n_coiled']} | {h1['n_ncw']} | {_fmt(h1['coiled_clean15'])}% | {_fmt(h1['ncw_clean15'])}% | {_fmt(h1['delta'])}pp |",
          f"| post-2024 | {h2['n_coiled']} | {h2['n_ncw']} | {_fmt(h2['coiled_clean15'])}% | {_fmt(h2['ncw_clean15'])}% | {_fmt(h2['delta'])}pp |",
          ""]

    # deep-ETF context
    L += ["## Deep TSX sector-ETF context (2001→, DIFFERENT cohort mechanic — NOT in the verdict)", ""]
    if "error" in etf:
        L += [f"_skipped — {etf['error']}_", ""]
    else:
        L += ["**Pre-stated caveat:** an ETF *is* its sector, so there is no sector-peer cohort. "
              "This treats the 9 sector ETFs as ONE cross-ETF cohort (breadth-of-sector-washout) — "
              "a genuinely different object from the per-name mechanic. Context only; it cannot and "
              "does not change the G-CA verdict.", "",
              f"Inception: {', '.join(f'{k} {v}' for k,v in etf['inception'].items())}. "
              f"Total fires {etf['n_fires']}.", "",
              "| stratum | n | clean15 | stop5 |",
              "|---|--:|--:|--:|",
              f"| ALL | {etf['ALL']['n']} | {_fmt(etf['ALL']['clean15'])}% | {_fmt(etf['ALL']['stop5'])}% |",
              f"| COILED (cross-ETF) | {etf['COILED']['n']} | {_fmt(etf['COILED']['clean15'])}% | {_fmt(etf['COILED']['stop5'])}% |",
              f"| NCW (cross-ETF) | {etf['NCW']['n']} | {_fmt(etf['NCW']['clean15'])}% | {_fmt(etf['NCW']['stop5'])}% |",
              f"| **Δ** | | **{_fmt(etf.get('delta_clean15_pp'))}pp** | |", ""]

    # survivorship + what-this-does-not-show
    L += ["## Survivorship bound (not a stamp)",
          "`canada_search/closes.parquet` is current-constituent (219 names on today's TSX); "
          "delisted losers are absent → durable-bottom liftoff rates are biased UP uniformly. "
          "The COILED-vs-NCW **spread** (both strata from the same survivor panel) is the object "
          "of interest and is far less sensitive to that level bias. Bound: a COILED-PASS here is "
          "an optimistic upper bound; a COILED-FAIL is conservative (survivorship only helps "
          "liftoff). No ex-US dead-name store → no worst-case delisted-imputation lower bound. "
          "The deep-ETF context is survivorship-clean.", "",
          "## What this does NOT show",
          "Only the COILED cohort-washout × bullish-divergence detector as a CA standout-board "
          "ranking bonus on the `m2d_s3d` trigger. It does NOT test other triggers, the wave-4 "
          "COILED-FIRE marker, theme-basket cohorts, volume/participation (no CA search-store "
          "volume), the deep-ETF cohort as a decision leg (context only, different mechanism), or "
          "any CA edge outside COILED (C1 commodity→sector, C-BANK, momentum — separate batteries, "
          "resolved in masterplan §6.1). A CA NO-GO/KILL is a verdict on THIS engine's portability "
          "to Canada, not on whether Canada has any tradable durable-bottom timing edge.", "",
          "---",
          "_Harness `research/entry_timing/wave3_ca.py` (fork of `wave3.py` close-only path; "
          "leak-free math reused verbatim). Pre-reg `research/COILED_CA_PREREG.md`. "
          f"DSR family budget {PROGRAM_N_TRIALS} via `TrialLedger.with_declared_budget`. No wiring._"]
    return "\n".join(L)


@register_trials(FAMILY, budget=PROGRAM_N_TRIALS, basis="estimated",
                 reason="masterplan §6 program-level DSR budget (both markets)")
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    # register the DSR family budget floor (idempotent)
    TrialLedger.with_declared_budget(PROGRAM_N_TRIALS, FAMILY)

    out_dir = ENTRY_TIMING / "wave3_ca_out"
    meta, events_df, fires_dfs = run_ca_names(args.workers, out_dir)
    fires_m = fires_dfs["m2d_s3d"]
    if len(fires_m) == 0:
        print("NO m2d_s3d fires — aborting")
        return 1

    gate = apply_gate(fires_m)
    print("\n=== deep TSX sector-ETF context (different mechanism) ===")
    etf = run_deep_etfs()

    report = render(meta, events_df, fires_dfs, gate, etf)
    from lib import config
    rpt = ROOT / config.load()["storage"]["reports_dir"] / "coiled-ca-phase0.md"
    rpt.write_text(report)
    (out_dir / "gate.json").write_text(json.dumps(gate, indent=2, default=str))

    print(f"\n[report] {rpt}")
    print(f"[verdict] {gate['verdict']} — {'; '.join(gate['reasons'])}")
    print(f"  clean15: COILED {gate['clean15']['coiled']} vs NCW {gate['clean15']['ncw']} "
          f"(Δ {gate['clean15']['delta']}pp); stop5 Δ {gate['stop5']['delta']}pp")
    print(f"  n_COILED {gate['n_coiled']}; per-name {gate['per_name']['pct']}%; "
          f"boot 90% LB {gate['bootstrap'].get('lb90_one_sided')}pp; "
          f"split h1 {gate['split_half']['h1_pre_2024']['delta']} / h2 {gate['split_half']['h2_post_2024']['delta']}")
    return 0


if __name__ == "__main__":
    import logging
    logging.disable(logging.CRITICAL)
    sys.exit(main())
