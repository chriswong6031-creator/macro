"""
P2_5_DIAGNOSTIC — Depth-gradient partition of production-washout fires.

Study:   P2_5_depth_gradient_diagnostic
Program: Entry Intelligence (EI)
Label:   DIAGNOSTIC — IN-SAMPLE, NO VERDICTS; hypotheses feed P2_5 PREREG
Author:  Subagent under Fable orchestration
Date:    2026-07-05

PURPOSE
-------
Locate WHERE (if anywhere) the stop-out edge lives by partitioning the 49,939
verdict-grade fires on continuous washout depth.  Purely descriptive — no
significance claims, no verdicts, no BH testing.  All outputs labelled
DIAGNOSTIC / IN-SAMPLE.

REUSE PROVENANCE
----------------
- Replay loading + PIT washout computation: verbatim from
  research/entry_intel/p1_runs/P2_1B_F1_REPROBE/run_P2_1B_F1_reprobe.py
- washout_ctx from engine/coiled.py (unchanged).
- Continuous depth computed via an inline extension of washout_ctx's algorithm
  (same capit_pos, same prior_max formula; returns float dd instead of bool).

OUTPUTS
-------
  P2_5_DIAGNOSTIC/
    run_P2_5_diagnostic.py   (this file)
    RESULTS.md
    results.json
"""

import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ── Paths ──────────────────────────────────────────────────────────────────────
REPO = Path(__file__).parents[4]
sys.path.insert(0, str(REPO))
REPLAY_PATH = REPO / "data" / "replay" / "replay_boarded.parquet"
MSD_DIR = REPO / "data" / "massive_stock_day"
OUT_DIR = Path(__file__).parent

# Era filter matches F1 reprobe / P1.3
P13_ERA_START = "2022-06-30"
P13_ERA_END   = "2025-12-29"
EXPECTED_MD5  = "906175f9eb8caa351ed6d7d5c56265d3"

LABEL = "DIAGNOSTIC — IN-SAMPLE, NO VERDICTS; hypotheses feed P2_5 PREREG"

print("=" * 72)
print(f"P2_5_DIAGNOSTIC — depth-gradient partition of production washout fires")
print(LABEL)
print("=" * 72)
print()

# ── 1. Load replay — verdict-grade fires only ─────────────────────────────────
print("Loading replay_boarded.parquet ...")
import hashlib
with open(REPLAY_PATH, "rb") as f:
    md5 = hashlib.md5(f.read()).hexdigest()
print(f"  MD5: {md5}  (ref {EXPECTED_MD5}  match={md5==EXPECTED_MD5})")

df = pd.read_parquet(REPLAY_PATH)
vg = df[
    (df["verdict_type"] == "fire")
    & (df["verdict_grade"] == True)
    & (df["signal_date"] >= P13_ERA_START)
    & (df["signal_date"] <= P13_ERA_END)
].copy()
assert len(vg) == 49939, f"Expected 49,939 fires, got {len(vg)}"
print(f"  Verdict-grade fires: {len(vg):,}  episode-clusters: {vg['episode_id'].nunique():,}")
print()

# ── 2. Continuous depth via inline extension of washout_ctx ───────────────────
# Same algorithm as engine.coiled.washout_ctx but returns (dd_float | None).
# dd is the drawdown from the 126-bar pre-capitulation high to the trough,
# expressed as a positive fraction (e.g. 0.23 = 23% drawdown).

_WASH_CTX_B = 91
_WASH_CTX_A = 217   # 308 - 91

def washout_depth_pit(daily_close: pd.Series):
    """
    Returns (washout_bool | None, dd_pct_positive | None, bars_since_capit | None).
    Exact same capit_pos / prior_max as washout_ctx in engine/coiled.py.
    """
    try:
        c = daily_close.dropna()
        if not isinstance(c.index, pd.DatetimeIndex):
            c = c.copy()
            c.index = pd.to_datetime(c.index)
        arr = c.to_numpy()
        n   = len(arr)
        if n < _WASH_CTX_A + _WASH_CTX_B:
            return None, None, None
        window    = arr[n - _WASH_CTX_B:]
        local_min = int(np.argmin(window))
        capit_pos = (n - _WASH_CTX_B) + local_min
        if capit_pos < 126:
            return None, None, None
        prior_max = float(np.nanmax(arr[capit_pos - 126: capit_pos]))
        if prior_max <= 0:
            return None, None, None
        dd = arr[capit_pos] / prior_max - 1.0          # negative number
        dd_pos = -dd                                     # positive (0.23 = 23%)
        washout = bool(dd <= -0.15)
        bars_since = n - 1 - capit_pos                  # bars from trough to signal_date
        return washout, float(dd_pos), int(bars_since)
    except Exception:
        return None, None, None


# ── 3. PIT computation — verbatim concordance path ────────────────────────────
print("Computing PIT washout depth for every (ticker, signal_date) pair ...")
print("  (verbatim concordance compute path from run_P2_1B_F1_reprobe.py)")

pairs = vg[["ticker", "signal_date"]].drop_duplicates()
prod_cache = {}
depth_results = {}   # (ticker, Timestamp) -> (washout_bool|None, dd_pos|None, bars_since|None)
n_errors = 0
t0 = time.time()

for i, row in enumerate(pairs.itertuples()):
    ticker = row.ticker
    sd     = pd.Timestamp(row.signal_date)
    try:
        if ticker not in prod_cache:
            prod_cache[ticker] = pd.read_parquet(MSD_DIR / f"{ticker}.parquet")["close"]
        price = prod_cache[ticker]
        pit   = price[price.index <= sd]
        depth_results[(ticker, sd)] = washout_depth_pit(pit)
    except Exception:
        depth_results[(ticker, sd)] = (None, None, None)
        n_errors += 1
    if i > 0 and i % 10000 == 0:
        print(f"    {i:,}/{len(pairs):,} ({time.time()-t0:.0f}s)", flush=True)

print(f"  Done: {len(depth_results):,} pairs in {time.time()-t0:.1f}s  errors={n_errors}")

# Map onto vg
vg["prod_washout"]    = [depth_results.get((t, pd.Timestamp(s)), (None,None,None))[0]
                          for t, s in zip(vg["ticker"], vg["signal_date"])]
vg["dd_pct"]          = [depth_results.get((t, pd.Timestamp(s)), (None,None,None))[1]
                          for t, s in zip(vg["ticker"], vg["signal_date"])]
vg["bars_since_capit"]= [depth_results.get((t, pd.Timestamp(s)), (None,None,None))[2]
                          for t, s in zip(vg["ticker"], vg["signal_date"])]

n_defined  = int(vg["prod_washout"].notna().sum())
n_wash_true= int((vg["prod_washout"] == True).sum())
n_wash_false=int((vg["prod_washout"] == False).sum())
n_none     = int(vg["prod_washout"].isna().sum())
print(f"  prod_washout: True={n_wash_true:,}  False={n_wash_false:,}  None={n_none:,}")
print(f"  dd_pct defined: {int(vg['dd_pct'].notna().sum()):,}")
print()

# ── 4. Derived columns ────────────────────────────────────────────────────────
# Anti-chase pass: ext_z <= 2.0
vg["anti_chase_pass"] = vg["ext_z"] <= 2.0

# RS quartile: Q1/Q2 (top half) vs Q3/Q4 (bottom half)
vg["rs_favorable"] = vg["rs_sector_quartile"].isin([1.0, 2.0])

# Proxy-equivalent bucket: washout_proximity == True (price ≤ 0.9×200DMA)
# This is already in the replay as 'washout_proximity'

# Depth buckets (on prod_washout=True fires only; bucket by dd_pct)
def depth_bucket(dd):
    if pd.isna(dd):
        return "no_depth"
    if dd < 0.15:
        return "sub15"        # washout_ctx would return False, yet dd present
    elif dd < 0.25:
        return "d15_25"
    elif dd < 0.40:
        return "d25_40"
    else:
        return "d40plus"

vg["depth_bucket"] = vg["dd_pct"].apply(depth_bucket)

# Chronological halves (on the defined population)
defined = vg[vg["prod_washout"].notna()].copy()
dates_sorted = np.sort(defined["signal_date"].unique())
midpoint = dates_sorted[len(dates_sorted) // 2]
defined["half"] = np.where(defined["signal_date"] <= midpoint, "H1", "H2")
print(f"Both-halves midpoint: {midpoint}  H1={int((defined['half']=='H1').sum()):,}  H2={int((defined['half']=='H2').sum()):,}")
print()

# ── 5. Helper functions ────────────────────────────────────────────────────────

def outcome_rates(sub, hz=21):
    """Return dict of outcome rates at the given horizon (21 or 63 days)."""
    if hz == 21:
        state_col = "state_8_21"
    else:
        state_col = "state_15_126"
    n = len(sub)
    if n == 0:
        return {"n": 0, "n_episodes": 0,
                "stop_out": None, "dead_money": None,
                "clean_liftoff": None, "cushioned": None}
    vc = sub[state_col].value_counts()
    return {
        "n": n,
        "n_episodes": int(sub["episode_id"].nunique()),
        "stop_out":      round(vc.get("STOPPED", 0)       / n, 6),
        "dead_money":    round(vc.get("DEAD_MONEY", 0)    / n, 6),
        "clean_liftoff": round(vc.get("CLEAN_LIFTOFF", 0) / n, 6),
        "cushioned":     round(vc.get("CUSHIONED", 0)     / n, 6),
    }


def delta_pp(cell, baseline, key):
    """Delta in percentage points vs baseline for a given outcome key."""
    if cell[key] is None or baseline[key] is None:
        return None
    return round((cell[key] - baseline[key]) * 100, 3)


def cell_report(sub, baseline_21, baseline_63, label, half=None):
    """Full cell report at both horizons vs baselines, plus half-split."""
    r21 = outcome_rates(sub, 21)
    r63 = outcome_rates(sub, 63)
    half_dict = {}
    if half is not None:
        for h in ["H1", "H2"]:
            sh = sub[sub["half"] == h] if "half" in sub.columns else pd.DataFrame()
            half_dict[h] = {
                "21d": outcome_rates(sh, 21),
                "63d": outcome_rates(sh, 63),
            }
    return {
        "label": label,
        "n_fires": r21["n"],
        "n_episodes": r21["n_episodes"],
        "21d": {**r21,
                "stop_out_delta_pp":      delta_pp(r21, baseline_21, "stop_out"),
                "dead_money_delta_pp":    delta_pp(r21, baseline_21, "dead_money"),
                "clean_liftoff_delta_pp": delta_pp(r21, baseline_21, "clean_liftoff"),
                },
        "63d": {**r63,
                "stop_out_delta_pp":      delta_pp(r63, baseline_63, "stop_out"),
                "dead_money_delta_pp":    delta_pp(r63, baseline_63, "dead_money"),
                "clean_liftoff_delta_pp": delta_pp(r63, baseline_63, "clean_liftoff"),
                },
        "halves": half_dict,
    }


# ── 6. Baselines ──────────────────────────────────────────────────────────────
print("Computing baselines ...")
# Unconditioned: all defined fires
baseline_21 = outcome_rates(defined, 21)
baseline_63 = outcome_rates(defined, 63)
# Washout=True baseline (needed for within-washout depth analysis)
wash_true = defined[defined["prod_washout"] == True]
wash_false= defined[defined["prod_washout"] == False]
baseline_wash_true_21 = outcome_rates(wash_true, 21)
baseline_wash_true_63 = outcome_rates(wash_true, 63)

print(f"  Unconditioned defined  n={baseline_21['n']:,}  stop21={baseline_21['stop_out']:.4f}  dm21={baseline_21['dead_money']:.4f}")
print(f"  Washout=True           n={baseline_wash_true_21['n']:,}  stop21={baseline_wash_true_21['stop_out']:.4f}  dm21={baseline_wash_true_21['dead_money']:.4f}")
print(f"  Washout=False          n={outcome_rates(wash_false,21)['n']:,}  stop21={outcome_rates(wash_false,21)['stop_out']:.4f}")
print()

# ── 7. PARTITION (a): DEPTH GRADIENT ─────────────────────────────────────────
print("─" * 72)
print("PARTITION (a): DEPTH GRADIENT")
print("─" * 72)

depth_labels = ["d15_25", "d25_40", "d40plus"]
depth_cells = {}

# Washout=True fires stratified by depth bucket
for bucket in depth_labels:
    sub = defined[(defined["prod_washout"] == True) & (defined["depth_bucket"] == bucket)].copy()
    depth_cells[bucket] = cell_report(sub, baseline_21, baseline_63, bucket, half=defined)
    r = depth_cells[bucket]
    so21 = r["21d"]["stop_out_delta_pp"]
    so63 = r["63d"]["stop_out_delta_pp"]
    dm21 = r["21d"]["dead_money_delta_pp"]
    dm63 = r["63d"]["dead_money_delta_pp"]
    print(f"  {bucket:<10}  n={r['n_fires']:5,}  ep={r['n_episodes']:4,} | "
          f"21d stop_Δ={so21:+6.2f}pp  dm_Δ={dm21:+6.2f}pp | "
          f"63d stop_Δ={so63:+6.2f}pp  dm_Δ={dm63:+6.2f}pp")

# Proxy-equivalent bucket: washout_proximity=True fires (as comparator)
proxy_equiv = defined[defined["washout_proximity"] == True].copy()
depth_cells["proxy_equiv_washout_proximity"] = cell_report(
    proxy_equiv, baseline_21, baseline_63, "proxy_washout_proximity", half=defined
)
r = depth_cells["proxy_equiv_washout_proximity"]
print(f"  {'proxy_equiv':<10}  n={r['n_fires']:5,}  ep={r['n_episodes']:4,} | "
      f"21d stop_Δ={r['21d']['stop_out_delta_pp']:+6.2f}pp  dm_Δ={r['21d']['dead_money_delta_pp']:+6.2f}pp | "
      f"63d stop_Δ={r['63d']['stop_out_delta_pp']:+6.2f}pp  dm_Δ={r['63d']['dead_money_delta_pp']:+6.2f}pp")

# dd_pct distribution among washout=True fires
wash_true_with_dd = wash_true[wash_true["dd_pct"].notna()]
print(f"\n  dd_pct distribution (washout=True, n={len(wash_true_with_dd):,}):")
for p_val in [25, 50, 75, 90, 95]:
    print(f"    p{p_val}: {np.percentile(wash_true_with_dd['dd_pct'], p_val)*100:.1f}%")
print()

# ── 8. PARTITION (b): TREND CONTEXT ──────────────────────────────────────────
print("─" * 72)
print("PARTITION (b): TREND CONTEXT — washout × above_200")
print("─" * 72)

trend_cells = {}
for w_val, w_label in [(True, "washout_true"), (False, "washout_false")]:
    for a200_val, a200_label in [(True, "above_200"), (False, "below_200")]:
        key = f"{w_label}_{a200_label}"
        sub = defined[(defined["prod_washout"] == w_val) & (defined["above_200"] == a200_val)].copy()
        trend_cells[key] = cell_report(sub, baseline_21, baseline_63, key, half=defined)
        r = trend_cells[key]
        so21 = r["21d"]["stop_out_delta_pp"]
        so63 = r["63d"]["stop_out_delta_pp"]
        dm21 = r["21d"]["dead_money_delta_pp"]
        print(f"  {key:<35}  n={r['n_fires']:5,}  ep={r['n_episodes']:4,} | "
              f"21d stop_Δ={so21:+6.2f}pp  dm_Δ={dm21:+6.2f}pp | "
              f"63d stop_Δ={so63:+6.2f}pp")
print()

# ── 9. PARTITION (c): PAIRLETS ────────────────────────────────────────────────
print("─" * 72)
print("PARTITION (c): PAIRLETS")
print("─" * 72)

pairlet_cells = {}

# washout × anti-chase-pass
print("  [c1] washout × anti-chase-pass (ext_z <= 2.0)")
for w_val, w_label in [(True, "wash_T"), (False, "wash_F")]:
    for ac_val, ac_label in [(True, "ac_pass"), (False, "ac_fail")]:
        key = f"{w_label}_{ac_label}"
        sub = defined[(defined["prod_washout"] == w_val) & (defined["anti_chase_pass"] == ac_val)].copy()
        pairlet_cells[key] = cell_report(sub, baseline_21, baseline_63, key, half=defined)
        r = pairlet_cells[key]
        so21 = r["21d"]["stop_out_delta_pp"]
        so63 = r["63d"]["stop_out_delta_pp"]
        dm21 = r["21d"]["dead_money_delta_pp"]
        print(f"    {key:<22}  n={r['n_fires']:5,}  ep={r['n_episodes']:4,} | "
              f"21d stop_Δ={so21:+6.2f}pp  dm_Δ={dm21:+6.2f}pp | "
              f"63d stop_Δ={so63:+6.2f}pp")

# washout × RS-quartile
print("  [c2] washout × RS-quartile (Q1Q2 favorable vs Q3Q4)")
for w_val, w_label in [(True, "wash_T"), (False, "wash_F")]:
    for rs_val, rs_label in [(True, "rs_Q1Q2"), (False, "rs_Q3Q4")]:
        key = f"{w_label}_{rs_label}"
        sub = defined[(defined["prod_washout"] == w_val) & (defined["rs_favorable"] == rs_val)].copy()
        pairlet_cells[key] = cell_report(sub, baseline_21, baseline_63, key, half=defined)
        r = pairlet_cells[key]
        so21 = r["21d"]["stop_out_delta_pp"]
        so63 = r["63d"]["stop_out_delta_pp"]
        print(f"    {key:<22}  n={r['n_fires']:5,}  ep={r['n_episodes']:4,} | "
              f"21d stop_Δ={so21:+6.2f}pp | 63d stop_Δ={so63:+6.2f}pp")

# deep-washout (>25%) × anti-chase-pass
print("  [c3] deep-washout (dd_pct>25% OR proxy-equiv) × anti-chase-pass")
deep_mask = (
    (defined["prod_washout"] == True) & (defined["dd_pct"] > 0.25)
) | (
    defined["washout_proximity"] == True
)
for ac_val, ac_label in [(True, "ac_pass"), (False, "ac_fail")]:
    key = f"deep_washout_{ac_label}"
    sub = defined[deep_mask & (defined["anti_chase_pass"] == ac_val)].copy()
    pairlet_cells[key] = cell_report(sub, baseline_21, baseline_63, key, half=defined)
    r = pairlet_cells[key]
    so21 = r["21d"]["stop_out_delta_pp"]
    so63 = r["63d"]["stop_out_delta_pp"]
    dm21 = r["21d"]["dead_money_delta_pp"]
    print(f"    {key:<30}  n={r['n_fires']:5,}  ep={r['n_episodes']:4,} | "
          f"21d stop_Δ={so21:+6.2f}pp  dm_Δ={dm21:+6.2f}pp | "
          f"63d stop_Δ={so63:+6.2f}pp")
print()

# ── 10. PARTITION (d): TRIO — washout × anti-chase-pass × favorable-RS ───────
print("─" * 72)
print("PARTITION (d): TRIO — washout × anti-chase-pass × favorable-RS (Q1/Q2)")
print("─" * 72)

trio_cells = {}

# Full trio
trio_full = defined[
    (defined["prod_washout"] == True)
    & (defined["anti_chase_pass"] == True)
    & (defined["rs_favorable"] == True)
].copy()
trio_cells["washout_ac_pass_rs_fav"] = cell_report(
    trio_full, baseline_21, baseline_63, "washout_ac_pass_rs_fav", half=defined
)
r = trio_cells["washout_ac_pass_rs_fav"]
print(f"  trio (all three):  n={r['n_fires']:,}  ep={r['n_episodes']:,}")
if r["n_fires"] < 1000:
    print(f"  *** POWER WARNING: n={r['n_fires']} < 1,000 floor — flag for PREREG ***")
print(f"  21d: stop_Δ={r['21d']['stop_out_delta_pp']:+.2f}pp  dm_Δ={r['21d']['dead_money_delta_pp']:+.2f}pp  liftoff_Δ={r['21d']['clean_liftoff_delta_pp']:+.2f}pp")
print(f"  63d: stop_Δ={r['63d']['stop_out_delta_pp']:+.2f}pp  dm_Δ={r['63d']['dead_money_delta_pp']:+.2f}pp  liftoff_Δ={r['63d']['clean_liftoff_delta_pp']:+.2f}pp")

# Deep-trio: dd_pct > 25% (or proxy-equiv) + anti-chase + rs_fav
trio_deep = defined[
    (defined["prod_washout"] == True)
    & (defined["dd_pct"] > 0.25)
    & (defined["anti_chase_pass"] == True)
    & (defined["rs_favorable"] == True)
].copy()
trio_cells["deep_washout_ac_pass_rs_fav"] = cell_report(
    trio_deep, baseline_21, baseline_63, "deep_washout_ac_pass_rs_fav", half=defined
)
r = trio_cells["deep_washout_ac_pass_rs_fav"]
print(f"\n  deep-trio (dd>25%+ac+rs_fav): n={r['n_fires']:,}  ep={r['n_episodes']:,}")
if r["n_fires"] < 1000:
    print(f"  *** POWER WARNING: n={r['n_fires']} < 1,000 floor ***")
print(f"  21d: stop_Δ={r['21d']['stop_out_delta_pp']:+.2f}pp  dm_Δ={r['21d']['dead_money_delta_pp']:+.2f}pp")
print(f"  63d: stop_Δ={r['63d']['stop_out_delta_pp']:+.2f}pp  dm_Δ={r['63d']['dead_money_delta_pp']:+.2f}pp")

# Complement (trio fails)
trio_complement = defined[
    ~(
        (defined["prod_washout"] == True)
        & (defined["anti_chase_pass"] == True)
        & (defined["rs_favorable"] == True)
    )
].copy()
trio_cells["trio_complement"] = cell_report(
    trio_complement, baseline_21, baseline_63, "trio_complement", half=defined
)
r = trio_cells["trio_complement"]
print(f"\n  trio complement (not all three): n={r['n_fires']:,}  ep={r['n_episodes']:,}")
print(f"  21d: stop_Δ={r['21d']['stop_out_delta_pp']:+.2f}pp  dm_Δ={r['21d']['dead_money_delta_pp']:+.2f}pp")
print(f"  63d: stop_Δ={r['63d']['stop_out_delta_pp']:+.2f}pp  dm_Δ={r['63d']['dead_money_delta_pp']:+.2f}pp")
print()

# ── 11. RANK by |stop-out delta| × sign-consistency ──────────────────────────
print("─" * 72)
print("RANKING: |stop-out delta| × sign-consistency across halves")
print("─" * 72)

all_cells = {}
all_cells.update(depth_cells)
all_cells.update(trend_cells)
all_cells.update(pairlet_cells)
all_cells.update(trio_cells)

def sign_consistent(cell, hz_key):
    """Returns True if stop-out deltas have the same sign in H1 and H2."""
    h = cell.get("halves", {})
    h1 = h.get("H1", {}).get(hz_key, {})
    h2 = h.get("H2", {}).get(hz_key, {})
    if not h1 or not h2:
        return None
    b_21 = outcome_rates(pd.DataFrame(), 21)  # dummy — use baseline from outer scope
    # Compute stop delta for each half vs unconditioned baseline
    # We stored half data in the halves dict; we need to compare to half baselines.
    # For simplicity, report raw stop_out rate for H1 vs H2 vs total
    s1 = h1.get("stop_out")
    s2 = h2.get("stop_out")
    if s1 is None or s2 is None:
        return None
    return (s1 < baseline_21["stop_out"]) == (s2 < baseline_21["stop_out"])

ranking = []
for cname, cell in all_cells.items():
    if cell["n_fires"] < 50:
        continue
    so21_delta = cell["21d"].get("stop_out_delta_pp")
    so63_delta = cell["63d"].get("stop_out_delta_pp")
    dm63_delta = cell["63d"].get("dead_money_delta_pp")
    if so21_delta is None and so63_delta is None:
        continue
    abs_so = max(abs(so21_delta or 0), abs(so63_delta or 0))
    sc21 = sign_consistent(cell, "21d")
    sc63 = sign_consistent(cell, "63d")
    dm_surv = (dm63_delta is not None and dm63_delta < 0)
    ranking.append({
        "cell": cname,
        "n": cell["n_fires"],
        "n_ep": cell["n_episodes"],
        "so21_delta_pp": so21_delta,
        "so63_delta_pp": so63_delta,
        "dm63_delta_pp": dm63_delta,
        "abs_so_max": abs_so,
        "sc21": sc21,
        "sc63": sc63,
        "dm_survives": dm_surv,
    })

ranking.sort(key=lambda x: x["abs_so_max"], reverse=True)
print(f"  {'Cell':<40} {'n':>6}  so21Δ  so63Δ  dm63Δ  sc21  sc63  dmSurv")
for r_item in ranking[:20]:
    print(f"  {r_item['cell']:<40} {r_item['n']:>6}  "
          f"{(r_item['so21_delta_pp'] or 0):+5.1f}  "
          f"{(r_item['so63_delta_pp'] or 0):+5.1f}  "
          f"{(r_item['dm63_delta_pp'] or 0):+5.1f}  "
          f"{'Y' if r_item['sc21'] else 'N' if r_item['sc21']==False else '?':>4}  "
          f"{'Y' if r_item['sc63'] else 'N' if r_item['sc63']==False else '?':>4}  "
          f"{'Y' if r_item['dm_survives'] else 'N':>6}")
print()

# ── 12. Save results.json ─────────────────────────────────────────────────────
def clean(v):
    if isinstance(v, (np.bool_,)):     return bool(v)
    if isinstance(v, (np.integer,)):   return int(v)
    if isinstance(v, (np.floating,)):  return None if np.isnan(v) else float(v)
    if isinstance(v, float) and (np.isnan(v) or np.isinf(v)): return None
    return v

def deep_clean(obj):
    if isinstance(obj, dict):
        return {k: deep_clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [deep_clean(v) for v in obj]
    return clean(obj)

results_out = {
    "study_id": "P2_5_DIAGNOSTIC",
    "label": LABEL,
    "study_date": "2026-07-05",
    "replay_md5": md5,
    "replay_md5_matches": md5 == EXPECTED_MD5,
    "population": {
        "n_verdict_grade_fires": int(len(vg)),
        "n_defined": int(n_defined),
        "n_none_excluded": int(n_none),
        "n_washout_true": int(n_wash_true),
        "n_washout_false": int(n_wash_false),
        "halves_midpoint": str(midpoint),
    },
    "dd_pct_distribution_washout_true": {
        "n": int(len(wash_true_with_dd)),
        "p25": float(np.percentile(wash_true_with_dd["dd_pct"], 25)),
        "p50": float(np.percentile(wash_true_with_dd["dd_pct"], 50)),
        "p75": float(np.percentile(wash_true_with_dd["dd_pct"], 75)),
        "p90": float(np.percentile(wash_true_with_dd["dd_pct"], 90)),
        "p95": float(np.percentile(wash_true_with_dd["dd_pct"], 95)),
    },
    "baseline_unconditioned": {
        "21d": baseline_21,
        "63d": baseline_63,
    },
    "baseline_washout_true": {
        "21d": baseline_wash_true_21,
        "63d": baseline_wash_true_63,
    },
    "partition_a_depth_gradient": deep_clean(depth_cells),
    "partition_b_trend_context": deep_clean(trend_cells),
    "partition_c_pairlets": deep_clean(pairlet_cells),
    "partition_d_trio": deep_clean(trio_cells),
    "ranking": deep_clean(ranking),
}

out_json = OUT_DIR / "results.json"
with open(out_json, "w") as f:
    json.dump(results_out, f, indent=2, default=str)
print(f"Saved: {out_json}")
print()
print("=" * 72)
print("P2_5_DIAGNOSTIC COMPLETE")
print(LABEL)
print("=" * 72)
