"""ORC-RC-1 — Compound gauntlet time-shift placebo + P3 secondary month-block CI.

RE-CHECK — adjudication pending (Fable). No verdict is changed by this document.

Part 1: Replace the original G3 independent-draw timing placebo with a circular
time-shift placebo.  Each draw shifts the compound's entire real onset-date
sequence by one uniform random offset within the node's valid pool (wrapping),
preserving inter-onset spacing and clustering exactly.  2000 draws, seed 20260704.

Part 2: Re-express ep_in_onset_21d (sole BH-rejected secondary from P3) with a
calendar-month block bootstrap: resample calendar months with replacement (all
episodes in a drawn month move together), 2000 draws, seed 20260704.

Outputs:
  research/ORACLE_COMPOUND_TC_RECHECK.md
  research/oracle_compound_tc_recheck.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from scripts.oracle_screen import (  # noqa: E402
    _load_panel, _load_episodes, _load_spy, _load_rotation_groups,
    _compute_forward_returns, _ERA_CUTS,
)
from engine.oracle.compounds import (  # noqa: E402
    get_entry_dates, augment_panel_with_derived, load_registry,
)

H = 63
SEED = 20260704

IDS_S = [
    "A15_WASHOUT_OPP_OUT_2NODE",
    "A9_WASHOUT_SAME_OUTFLOW_DENSE",
    "A17_WASHOUT_SAME_OUT_NEG_VEL",
]
A17_MODERN_START = pd.Timestamp("2015-01-01")
A17_MODERN_OOS_SPLIT = pd.Timestamp("2020-12-31")


# ---------------------------------------------------------------------------
# Fast vectorized pool builder (mirrors oracle_screen logic exactly)
# ---------------------------------------------------------------------------

def _build_pool_vectorized(
    panel: pd.DataFrame,
    spy: pd.Series,
    h: int,
) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Build the valid-outcome pool for each node: (date_int64_ns, excess) arrays.

    Mirrors the oracle_screen._compute_forward_returns logic exactly:
      - entry at t -> execute at NEXT close (t+1 in node's sorted date index)
      - exit at exec_pos + h positions in node's index
      - SPY return: reindex spy to node dates, pct_change level,
          bench = spy_level[exit] / spy_level[exec] - 1
      - excess = node_return - bench_return

    Uses vectorized pandas/numpy operations instead of a Python date loop
    (~0.2s for 11 nodes vs ~13 min for the loop version).
    """
    nodes = panel.index.get_level_values("node").unique().tolist()
    pool: dict[str, tuple[np.ndarray, np.ndarray]] = {}

    for node in nodes:
        np_ = panel.xs(node, level="node")
        ret_s = np_["ret"].sort_index()
        dates = ret_s.index
        n = len(dates)
        if n <= h + 1:
            continue

        # SPY aligned to node dates (reindex + pct_change exactly as oracle_screen)
        spy_aligned = spy.reindex(dates)
        spy_ret_aligned = spy_aligned.pct_change(fill_method=None).fillna(0)
        spy_lvl = (1 + spy_ret_aligned).cumprod()

        # Node price level
        price_lvl = (1 + ret_s.fillna(0)).cumprod()

        # Valid entry indices: 0..n-h-2 (exec at 1..n-h-1, exit at h+1..n-1)
        entry_idx = np.arange(0, n - h - 1)
        exec_idx = entry_idx + 1
        exit_idx = entry_idx + 1 + h

        exec_price = price_lvl.iloc[exec_idx].to_numpy(dtype=float)
        exit_price = price_lvl.iloc[exit_idx].to_numpy(dtype=float)
        node_ret = np.where(exec_price != 0, exit_price / exec_price - 1, np.nan)

        spy_exec = spy_lvl.iloc[exec_idx].to_numpy(dtype=float)
        spy_exit = spy_lvl.iloc[exit_idx].to_numpy(dtype=float)
        bench_ret = np.where(spy_exec != 0, spy_exit / spy_exec - 1, np.nan)

        excess = node_ret - bench_ret
        entry_dates = dates[entry_idx]

        valid = ~np.isnan(excess)
        if valid.any():
            pool[str(node)] = (
                entry_dates[valid].astype("int64").to_numpy(),
                excess[valid],
            )

    return pool


# ---------------------------------------------------------------------------
# Circular time-shift placebo (vectorized)
# ---------------------------------------------------------------------------

def _circular_shift_placebo(
    f: pd.DataFrame,
    pool_by_node: dict[str, tuple[np.ndarray, np.ndarray]],
    n_draws: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Vectorized circular time-shift placebo.

    For each node with compound hits:
      1. Map each real onset date to its position in the pool (sorted by date).
      2. Pre-generate n_draws random offsets (one per draw).
      3. For all draws simultaneously: shifted = (pos + offset) % pool_size.
      4. Look up excess values at shifted positions.

    Returns array of n_draws draw means.  All draws computed via numpy broadcasting,
    no Python loop over draws.
    """
    f = f.copy()
    f["_ed_ns"] = pd.to_datetime(f["entry_date"]).astype("int64")

    node_data: list[np.ndarray] = []  # each element: (n_draws, n_node_entries)

    for node, grp in f.groupby("node"):
        node_str = str(node)
        if node_str not in pool_by_node:
            continue
        pool_dates_ns, pool_excess = pool_by_node[node_str]
        pool_size = len(pool_dates_ns)
        if pool_size == 0:
            continue

        real_dates_ns = grp["_ed_ns"].to_numpy(dtype="int64")
        # Nearest pool position for each real date
        positions = np.searchsorted(pool_dates_ns, real_dates_ns, side="left")
        positions = np.clip(positions, 0, pool_size - 1)

        # n_draws offsets for this node
        offsets = rng.integers(0, pool_size, size=n_draws)  # (n_draws,)
        # Shifted positions: (n_draws, n_entries) via broadcasting
        shifted = (positions[np.newaxis, :] + offsets[:, np.newaxis]) % pool_size
        # Excess at shifted positions: (n_draws, n_entries)
        shifted_excess = pool_excess[shifted]
        node_data.append(shifted_excess)

    if not node_data:
        return np.full(n_draws, np.nan)

    # Concat all nodes: (n_draws, total_entries); mean over entries per draw
    combined = np.concatenate(node_data, axis=1)
    return np.nanmean(combined, axis=1)


# ---------------------------------------------------------------------------
# Original placebo (reproduction gate)
# ---------------------------------------------------------------------------

def _run_original_placebo(
    f: pd.DataFrame,
    real: float,
    urn: dict[str, np.ndarray],
    n_orig: int = 500,
) -> tuple[float, float, bool]:
    """Reproduce the shipped independent-draw placebo."""
    cnt = f.groupby("node").size().to_dict()
    orig_draws = np.full(n_orig, np.nan)
    rng_orig = np.random.default_rng(20260704)
    for i in range(n_orig):
        vals = [
            rng_orig.choice(urn[nd], size=k, replace=True)
            for nd, k in cnt.items()
            if urn.get(nd) is not None and len(urn[nd])
        ]
        if vals:
            orig_draws[i] = np.concatenate(vals).mean()
    orig_p = float(np.mean(orig_draws >= real))
    orig_p95 = float(np.nanpercentile(orig_draws, 95))
    orig_g3 = bool(real > orig_p95)
    return orig_p, orig_p95, orig_g3


# ---------------------------------------------------------------------------
# Part 1
# ---------------------------------------------------------------------------

def run_part1(
    data_dir: Path,
    compounds_dir: Path,
    n_draws: int,
    seed: int,
) -> dict:
    rng = np.random.default_rng(seed)

    print("[Part 1] Loading panel, episodes, spy...", flush=True)
    panel = augment_panel_with_derived(_load_panel(data_dir, "s"))
    episodes = _load_episodes(data_dir, "s")
    spy = _load_spy(data_dir)
    rg = _load_rotation_groups(data_dir)

    # Compound registry
    reg: dict[str, dict] = {}
    for c in load_registry(compounds_dir):
        reg[c["id"]] = c
    main_compounds = data_dir / "oracle" / "compounds"
    if main_compounds.exists() and main_compounds != compounds_dir:
        for c in load_registry(main_compounds):
            if c["id"] not in reg:
                reg[c["id"]] = c

    # Fast vectorized pool build (~0.2s)
    print("[Part 1] Building pool (vectorized)...", flush=True)
    pool_by_node = _build_pool_vectorized(panel, spy, H)
    print(f"  Pool: {len(pool_by_node)} nodes, sizes: { {n: len(d) for n, (d, _) in pool_by_node.items()} }", flush=True)

    # urn for original independent-draw placebo (reproduction gate)
    urn: dict[str, np.ndarray] = {n: e for n, (d, e) in pool_by_node.items()}

    split_s = pd.Timestamp("2019-12-31")
    results: dict[str, dict] = {}

    for cid in IDS_S:
        if cid not in reg:
            print(f"[skip] {cid} not in registry", flush=True)
            continue

        print(f"\n[Part 1] {cid}", flush=True)
        comp = reg[cid]
        ed = get_entry_dates(comp, panel, episodes, rg)
        fwd = _compute_forward_returns(ed, panel, spy, [H], "s")
        f = fwd[fwd.horizon_d == H].dropna(subset=["excess"]).copy()
        f["ed"] = pd.to_datetime(f["entry_date"])
        real = float(f["excess"].mean())
        n = len(f)
        hit = float((f["excess"] > 0).mean())

        # G1 full-history OOS
        dev = f[f["ed"] <= split_s]["excess"]
        hold = f[f["ed"] > split_s]["excess"]
        dv = float(dev.mean())
        hv = float(hold.mean())
        hh = float((hold > 0).mean()) if len(hold) else float("nan")
        g1_full = bool(
            (np.sign(hv) == np.sign(dv)) and (hh >= 0.52) and (len(hold) >= 100)
        )

        print(f"  n={n} eff63={real*100:+.2f}% hit={hit*100:.1f}%", flush=True)
        print(f"  G1: dev n={len(dev)} eff={dv*100:+.2f}% | hold n={len(hold)} eff={hv*100:+.2f}% hit={hh*100:.1f}% -> {'PASS' if g1_full else 'FAIL'}", flush=True)

        # G2 per-era
        pos = 0
        for era, _, _ in _ERA_CUTS:
            s = f[f["era"] == era]["excess"]
            if len(s) >= 20:
                pos += int(float(s.mean()) > 0)
        print(f"  G2: {pos}/4 eras positive", flush=True)

        # Original G3
        orig_p, orig_p95, orig_g3 = _run_original_placebo(f, real, urn)
        print(f"  ORIG G3 (n=500): p95={orig_p95*100:+.2f}% p={orig_p:.4f} -> {'PASS' if orig_g3 else 'FAIL'}", flush=True)

        # New G3: circular time-shift
        print(f"  NEW G3 (time-shift, n={n_draws})...", flush=True)
        ts_draws = _circular_shift_placebo(f, pool_by_node, n_draws, rng)
        ts_p = float(np.mean(ts_draws >= real))
        ts_p95 = float(np.nanpercentile(ts_draws, 95))
        ts_g3 = bool(real > ts_p95)
        print(f"  NEW G3: real={real*100:+.2f}% p95={ts_p95*100:+.2f}% p={ts_p:.4f} -> {'PASS' if ts_g3 else 'FAIL'}", flush=True)

        rec: dict = {
            "id": cid, "n": n,
            "effect_63d": round(real, 6), "hit_63d": round(hit, 4),
            "g1_oos_full": g1_full,
            "g1_dev_n": int(len(dev)), "g1_dev_eff": round(dv, 6),
            "g1_hold_n": int(len(hold)), "g1_hold_eff": round(hv, 6),
            "g1_hold_hit": round(hh, 4) if not np.isnan(hh) else None,
            "shipped_placebo_p": round(orig_p, 4),
            "shipped_placebo_p95": round(orig_p95, 6),
            "shipped_g3": orig_g3,
            "timeshift_placebo_p": round(ts_p, 4),
            "timeshift_placebo_p95": round(ts_p95, 6),
            "timeshift_g3": ts_g3,
        }

        # A17: also run within-modern regime
        if "A17" in cid:
            f_mod = f[f["ed"] >= A17_MODERN_START].copy()
            real_mod = float(f_mod["excess"].mean())
            n_mod = len(f_mod)
            hit_mod = float((f_mod["excess"] > 0).mean())
            dev_mod = f_mod[f_mod["ed"] <= A17_MODERN_OOS_SPLIT]["excess"]
            hold_mod = f_mod[f_mod["ed"] > A17_MODERN_OOS_SPLIT]["excess"]
            dv_mod = float(dev_mod.mean()) if len(dev_mod) else float("nan")
            hv_mod = float(hold_mod.mean()) if len(hold_mod) else float("nan")
            hh_mod = float((hold_mod > 0).mean()) if len(hold_mod) else float("nan")
            g1_mod = bool(
                len(hold_mod) >= 100
                and not np.isnan(hh_mod) and hh_mod >= 0.52
                and not np.isnan(dv_mod) and not np.isnan(hv_mod)
                and (np.sign(hv_mod) == np.sign(dv_mod))
            )
            print(f"  A17 MODERN (2015+): n={n_mod} eff={real_mod*100:+.2f}% hit={hit_mod*100:.1f}%", flush=True)
            print(f"    dev(<=2020) n={len(dev_mod)} eff={dv_mod*100:+.2f}% | hold(>2020) n={len(hold_mod)} eff={hv_mod*100:+.2f}% hit={hh_mod*100:.1f}% G1={'PASS' if g1_mod else 'FAIL'}", flush=True)

            orig_p_mod, orig_p95_mod, orig_g3_mod = _run_original_placebo(f_mod, real_mod, urn)
            print(f"  A17 MODERN ORIG G3 (n=500): p={orig_p_mod:.4f} -> {'PASS' if orig_g3_mod else 'FAIL'}", flush=True)

            ts_draws_mod = _circular_shift_placebo(f_mod, pool_by_node, n_draws, rng)
            ts_p_mod = float(np.mean(ts_draws_mod >= real_mod))
            ts_p95_mod = float(np.nanpercentile(ts_draws_mod, 95))
            ts_g3_mod = bool(real_mod > ts_p95_mod)
            print(f"  A17 MODERN NEW G3 (n={n_draws}): p={ts_p_mod:.4f} -> {'PASS' if ts_g3_mod else 'FAIL'}", flush=True)

            rec.update({
                "a17_modern_n": n_mod, "a17_modern_eff": round(real_mod, 6),
                "a17_modern_hit": round(hit_mod, 4), "a17_modern_g1": g1_mod,
                "a17_modern_dev_n": int(len(dev_mod)),
                "a17_modern_hold_n": int(len(hold_mod)),
                "a17_modern_hold_eff": round(hv_mod, 6) if not np.isnan(hv_mod) else None,
                "a17_modern_hold_hit": round(hh_mod, 4) if not np.isnan(hh_mod) else None,
                "a17_modern_shipped_placebo_p": round(orig_p_mod, 4),
                "a17_modern_shipped_g3": orig_g3_mod,
                "a17_modern_timeshift_p": round(ts_p_mod, 4),
                "a17_modern_timeshift_g3": ts_g3_mod,
            })

        results[cid] = rec

    return results


# ---------------------------------------------------------------------------
# Part 2
# ---------------------------------------------------------------------------

def run_part2(data_dir: Path, n_draws: int, seed: int) -> dict:
    print("\n[Part 2] ep_in_onset_21d calendar-month block bootstrap", flush=True)
    ep_path = data_dir / "oracle" / "episodes_s.parquet"
    episodes = pd.read_parquet(ep_path)

    ep = episodes[
        (episodes["direction"] == "in")
        & episodes["outcome_rs_21d"].notna()
        & (episodes["outcome_mature_21d"] == True)  # noqa: E712
    ].copy()
    ep["onset_dt"] = pd.to_datetime(ep["onset_date"])
    ep = ep.sort_values("onset_dt").reset_index(drop=True)

    n = len(ep)
    print(f"  N episodes (in, 21d mature): {n}", flush=True)
    if n == 0:
        return {"error": "No valid in-direction 21d mature episodes found"}

    vals = ep["outcome_rs_21d"].to_numpy(dtype=float)
    real_mean = float(np.mean(vals))
    print(f"  Real mean (DA, 21d, in): {real_mean*100:+.4f}%", flush=True)

    ep["ym"] = ep["onset_dt"].dt.to_period("M")
    months = sorted(ep["ym"].unique().tolist())
    month_groups = [ep[ep["ym"] == m].index.tolist() for m in months]
    n_months = len(months)
    epm_vals = [len(g) for g in month_groups]
    print(f"  Months: {n_months} ({months[0]} to {months[-1]})", flush=True)
    print(f"  Epi/month: min={min(epm_vals)} max={max(epm_vals)} mean={np.mean(epm_vals):.1f}", flush=True)

    rng = np.random.default_rng(seed)
    boot_means = np.empty(n_draws)
    for i in range(n_draws):
        drawn = rng.integers(0, n_months, size=n_months)
        idx: list[int] = []
        for m_i in drawn:
            idx.extend(month_groups[int(m_i)])
        boot_means[i] = float(np.mean(vals[idx]))

    ci_lo = float(np.percentile(boot_means, 2.5))
    ci_hi = float(np.percentile(boot_means, 97.5))
    one_sided_p = float(np.mean(boot_means <= 0))
    print(f"  Month-block 95% CI: [{ci_lo*100:+.4f}%, {ci_hi*100:+.4f}%]", flush=True)
    print(f"  One-sided p (H1: mean>0): {one_sided_p:.4f}", flush=True)

    return {
        "cell_id": "ep_in_onset_21d",
        "n_episodes": n, "n_months": n_months,
        "month_range": [str(months[0]), str(months[-1])],
        "real_mean": round(real_mean, 6),
        "episodes_per_month_min": int(min(epm_vals)),
        "episodes_per_month_max": int(max(epm_vals)),
        "episodes_per_month_mean": round(float(np.mean(epm_vals)), 2),
        "episodes_per_month_median": round(float(np.median(epm_vals)), 2),
        "month_block_boot_ci_lo": round(ci_lo, 6),
        "month_block_boot_ci_hi": round(ci_hi, 6),
        "month_block_boot_p_onesided": round(one_sided_p, 4),
        "n_draws": n_draws, "seed": seed,
        "shipped_episode_block_ci_lo": 0.0013,
        "shipped_episode_block_ci_hi": 0.0116,
        "shipped_episode_block_boot_p": 0.0075,
        "episodes_per_month_distribution": {
            str(m): int(len(month_groups[i])) for i, m in enumerate(months)
        },
    }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _p(v, d=2):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "n/a"
    return f"{v*100:+.{d}f}%"


def _f(v, d=4):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "n/a"
    return f"{v:.{d}f}"


def _write_report(p1: dict, p2: dict, out_md: Path, out_json: Path, n_draws: int, seed: int):
    a15 = p1.get("A15_WASHOUT_OPP_OUT_2NODE", {})
    a9 = p1.get("A9_WASHOUT_SAME_OUTFLOW_DENSE", {})
    a17 = p1.get("A17_WASHOUT_SAME_OUT_NEG_VEL", {})

    md = [
        "# Oracle Compound + P3 Secondary — Time-Confound Re-Check (ORC-RC-1)",
        "",
        "**RE-CHECK — adjudication pending (Fable). No verdict is changed by this document.**",
        "",
        f"Date: 2026-07-07  |  Seed: {seed}  |  Draws: {n_draws} per part",
        "",
        "---",
        "",
        "## Part 1 — Compound Gauntlet: Circular Time-Shift Placebo",
        "",
        "### Methodology",
        "",
        "Shipped G3 (`_run_placebo`, oracle_gauntlet_compound.py :228-252): for each",
        "draw, independently resample count-matched outcomes per node from the full",
        "realizable-outcome pool.  Does not preserve temporal clustering — real onsets",
        "that concentrate in regimes get shuffled against random-regime draws.",
        "",
        "Circular time-shift: for each draw, each node's full real onset-date sequence is",
        "shifted by one uniform random integer offset in [0, pool_size) mod pool_size,",
        "landing each onset at pool_dates[(pool_position + offset) % pool_size].  Inter-",
        "onset spacing and temporal clustering are preserved exactly; count is matched",
        "by construction.  Pool built with the same entry→exec→exit logic as oracle_screen",
        "(vectorized for efficiency; excess values are identical).",
        "",
        "### Reproduction gate",
        "",
        "G1 full-history OOS (split 2019-12-31):",
        "",
        "| ID | n | eff₆₃ | dev eff | hold n | hold eff | hold hit | G1 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for cid, rec in [("A15_WASHOUT_OPP_OUT_2NODE", a15), ("A9_WASHOUT_SAME_OUTFLOW_DENSE", a9), ("A17_WASHOUT_SAME_OUT_NEG_VEL", a17)]:
        if not rec:
            md.append(f"| {cid} | MISSING | — | — | — | — | — | — |")
            continue
        g1 = "PASS" if rec.get("g1_oos_full") else "FAIL"
        md.append(f"| {cid} | {rec['n']} | {_p(rec.get('effect_63d'))} | {_p(rec.get('g1_dev_eff'))} | {rec.get('g1_hold_n','?')} | {_p(rec.get('g1_hold_eff'))} | {_p(rec.get('g1_hold_hit'))} | {g1} |")
    md += [
        "",
        "Reference (ORACLE_COMPOUND_GAUNTLET_R1.md):",
        "- A15: n=2351 eff=+1.30%, holdout +1.19%/53.4%/n=663, G1 PASS",
        "- A9: n=438 eff=+1.06%, holdout +2.27%/65.4%/n=191, G1 PASS",
        "- A17 full-history: dev=−0.03%, G1 FAIL (expected; modern-regime edge)",
        "",
        "### G3 side-by-side: shipped independent draws vs circular time-shift",
        "",
        f"| ID | scope | shipped p (n=500) | time-shift p (n={n_draws}) | shipped G3 | time-shift G3 |",
        "|---|---|---|---|---|---|",
    ]
    for label, rec, scope in [
        ("A15_WASHOUT_OPP_OUT_2NODE", a15, "full"),
        ("A9_WASHOUT_SAME_OUTFLOW_DENSE", a9, "full"),
        ("A17_WASHOUT_SAME_OUT_NEG_VEL", a17, "full"),
        ("A17 (modern 2015+)", a17, "modern"),
    ]:
        if not rec:
            md.append(f"| {label} | {scope} | n/a | n/a | n/a | n/a |")
            continue
        if scope == "modern":
            sp = rec.get("a17_modern_shipped_placebo_p")
            tp = rec.get("a17_modern_timeshift_p")
            sg = rec.get("a17_modern_shipped_g3")
            tg = rec.get("a17_modern_timeshift_g3")
        else:
            sp = rec.get("shipped_placebo_p")
            tp = rec.get("timeshift_placebo_p")
            sg = rec.get("shipped_g3")
            tg = rec.get("timeshift_g3")
        md.append(f"| {label} | {scope} | {_f(sp)} | {_f(tp)} | {'PASS' if sg else 'FAIL'} | {'PASS' if tg else 'FAIL'} |")
    md += [
        "",
        "### A17 modern-regime detail",
        "",
    ]
    if a17:
        md += [
            f"- Modern window (2015+): n={a17.get('a17_modern_n','?')}, eff63={_p(a17.get('a17_modern_eff'))}, hit={_p(a17.get('a17_modern_hit'))}",
            f"- Within-modern OOS (dev≤2020-12-31, hold>2020): hold n={a17.get('a17_modern_hold_n','?')}, eff={_p(a17.get('a17_modern_hold_eff'))}, hit={_p(a17.get('a17_modern_hold_hit'))}",
            f"- G1 within-modern: {'PASS' if a17.get('a17_modern_g1') else 'FAIL'}",
            f"- Shipped G3 (modern subset, n=500): p={_f(a17.get('a17_modern_shipped_placebo_p'))}",
            f"- Time-shift G3 (modern subset, n={n_draws}): p={_f(a17.get('a17_modern_timeshift_p'))}",
        ]
    else:
        md.append("A17 results not available.")
    md += [
        "",
        "---",
        "",
        "## Part 2 — P3 Secondary ep_in_onset_21d: Calendar-Month Block Bootstrap",
        "",
        "### Context",
        "",
        "The sole BH-rejected secondary from P3 is ep_in_onset_21d (raw p=0.0075, n=355).",
        "The shipped CI used 21-consecutive-episode blocks in detection order.",
        "Calendar-month blocks are a tighter temporal control: all episodes whose onset",
        "falls in the same (year, month) move together in each bootstrap draw.",
        "",
    ]
    if p2 and "error" not in p2:
        md += [
            "### Coverage stamp",
            "",
            f"- Episodes: {p2.get('n_episodes','?')} (in-direction, 21d mature outcome)",
            f"- Calendar months: {p2.get('n_months','?')} ({p2.get('month_range',['?','?'])[0]} to {p2.get('month_range',['?','?'])[1]})",
            f"- Episodes/month: min={p2.get('episodes_per_month_min','?')}, max={p2.get('episodes_per_month_max','?')}, mean={p2.get('episodes_per_month_mean','?'):.1f}, median={p2.get('episodes_per_month_median','?'):.1f}",
            "",
            "### Side-by-side: shipped episode-block vs calendar-month block",
            "",
            "| Method | Bootstrap 95% CI | One-sided p (H1: mean>0) |",
            "|---|---|---|",
            f"| Shipped (21-episode-block, n=2000) | [{_p(p2.get('shipped_episode_block_ci_lo'))}, {_p(p2.get('shipped_episode_block_ci_hi'))}] | {_f(p2.get('shipped_episode_block_boot_p'))} |",
            f"| Month-block (n={p2.get('n_draws',n_draws)}) | [{_p(p2.get('month_block_boot_ci_lo'))}, {_p(p2.get('month_block_boot_ci_hi'))}] | {_f(p2.get('month_block_boot_p_onesided'))} |",
            "",
            f"Real mean: {_p(p2.get('real_mean'), 4)}",
            "",
        ]
    else:
        err = p2.get("error", "unknown") if p2 else "Part 2 not run"
        md += [f"Part 2 not computed: {err}", ""]
    md += [
        "---",
        "",
        "*RE-CHECK artifact. Verdicts remain pending Fable adjudication.*",
        f"*Script: scripts/research/oracle_compound_tc_recheck.py  |  Seed: {seed}*",
        "",
    ]

    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(md), encoding="utf-8")
    print(f"\n[Output] {out_md}", flush=True)

    out_data = {
        "meta": {"seed": seed, "n_draws": n_draws,
                 "script": "scripts/research/oracle_compound_tc_recheck.py",
                 "date": "2026-07-07"},
        "part1_compound_timeshift_placebo": p1,
        "part2_p3_month_block_bootstrap": p2,
    }
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(out_data, indent=2, default=str), encoding="utf-8")
    print(f"[Output] {out_json}", flush=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-dir", type=Path,
                   default=Path("/Users/chriswong/Documents/Cluade/Macro Dashboard/data"))
    p.add_argument("--compounds-dir", type=Path, default=None)
    p.add_argument("--draws", type=int, default=2000)
    p.add_argument("--seed", type=int, default=SEED)
    args = p.parse_args()

    compounds_dir = args.compounds_dir or (ROOT / "data" / "oracle" / "compounds")

    print("=== ORC-RC-1 Time-Confound Re-Check ===", flush=True)
    print(f"data-dir: {args.data_dir}", flush=True)
    print(f"compounds-dir: {compounds_dir}", flush=True)
    print(f"draws: {args.draws}  seed: {args.seed}", flush=True)
    print(flush=True)

    results_p1 = run_part1(args.data_dir, compounds_dir, args.draws, args.seed)
    result_p2 = run_part2(args.data_dir, args.draws, args.seed)

    out_md = ROOT / "research" / "ORACLE_COMPOUND_TC_RECHECK.md"
    out_json = ROOT / "research" / "oracle_compound_tc_recheck.json"
    _write_report(results_p1, result_p2, out_md, out_json, args.draws, args.seed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
