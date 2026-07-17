"""RRI Stage-A replay gauntlet — one-shot study harness (off the render path).

Implements EXACTLY the frozen, operator-ratified preregs (PR #2725):
  research/RRI_CRASH_ANTIFIRE_PROGRAM.md      rulers R-A..R-D, family §4, grammar §6
  research/RRI_S1_LEG_FLOOR_ESCALATION_PREREG.md   cells 1-4
  research/RRI_S2_FX_TWOSIDED_STRESS_PREREG.md     cells 5-6
  research/RRI_S3_DRAWDOWN_VELOCITY_LEG_PREREG.md  cells 7-8

Run:    python -m scripts.rri_stage_a [--perms 2000] [--seed 20260717] [--out PATH]
Writes: data/risk_radar_intl/rri_study_results.json  (+ a stdout report)

Implementation choices the preregs left to the implementer — disclosed here and in the
RESULTS doc (two honest implementers should now converge):
  * Outcome estimator mirrors engine.risk_radar_intl_audit._grade_entry: base = as-of close,
    forward window = the NEXT 21 rows (asof excluded); days without 21 matured forward rows
    are excluded from the analysis universe on BOTH the observed and null sides.
  * Era gates re-run the full machinery on the era sub-window (masks, outcomes and circular
    shifts all restricted to the era region); same for split-half (per-market midpoint of its
    universe). An era/half with <3 pooled clusters prints SPARSE and caps the cell at ACCRUE.
  * p-values are the raw fraction of permutations with pooled cluster-hit rate >= observed
    (no +1 smoothing), exactly as the prereg words it.
  * S2 episode trough = the min close within [onset, onset+63]; de-escalation latency is
    censored at 63 sessions.
  * RNG: numpy default_rng(seed), per-market offsets drawn independently per permutation,
    uniform over [1, region_length-1].

House rules: no network, reads committed stores only, never imported by the build.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from engine.indicators import pct_rank_window
from engine.risk_radar_intl import (PROFILES, composite_series, _band, _BANDS, _read,
                                    _PCT_WIN)

MARKETS = ("kr", "jp", "tw", "in", "au", "gb", "ez")
GAP = 21                    # R-A cluster gap (sessions)
H21 = 21                    # primary horizon (rows AFTER the as-of row)
DD = -0.05                  # primary outcome threshold
Z = 1.645                   # one-sided 90% Wilson
LIFT_MIN = 1.25             # H1 lift gate vs the null mean
ERA_SPLIT = pd.Timestamp("2016-01-01")
N_FLOOR = 8                 # pooled cluster floor (primary cells)
ERA_FLOOR = 3               # pooled clusters per era/half below which SPARSE
FAMILY_ALPHA = 0.10         # BH-FDR within the 8-cell family
P_FLOOR = 0.05              # conjunctive hard floor


# ---------------------------------------------------------------- mechanics --
def wilson(hits: int, n: int, z: float = Z) -> tuple[float, float]:
    """One-sided Wilson lower/upper bounds at z."""
    if n == 0:
        return 0.0, 1.0
    ph = hits / n
    denom = 1 + z * z / n
    center = ph + z * z / (2 * n)
    half = z * np.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n))
    return (center - half) / denom, (center + half) / denom


def clusters(mask: np.ndarray, outcome: np.ndarray, gap: int = GAP) -> tuple[int, int]:
    """(n_clusters, n_cluster_hits) under the R-A gap rule; hit = any member day hits."""
    pos = np.flatnonzero(mask)
    if pos.size == 0:
        return 0, 0
    starts = np.flatnonzero(np.concatenate(([True], np.diff(pos) >= gap)))
    seg_hit = np.add.reduceat(outcome[pos].astype(np.int64), starts)
    return int(starts.size), int((seg_hit > 0).sum())


def perm_null(masks: dict[str, np.ndarray], outcomes: dict[str, np.ndarray],
              perms: int, rng: np.random.Generator) -> dict:
    """R-C null: per-market independent circular shifts of the FINAL mask, outcome fixed,
    identical re-clustering. Returns pooled null distribution + per-market null means."""
    pooled_rates = np.empty(perms)
    per_mkt_rates = {m: [] for m in masks}
    offsets = {m: rng.integers(1, max(2, len(masks[m])), size=perms) for m in masks}
    for i in range(perms):
        th = tc = 0
        for m, mask in masks.items():
            if mask.sum() == 0:
                continue
            sh = np.roll(mask, int(offsets[m][i]))
            c, h = clusters(sh, outcomes[m])
            th += h
            tc += c
            if c:
                per_mkt_rates[m].append(h / c)
        pooled_rates[i] = th / tc if tc else 0.0
    return {"pooled": pooled_rates,
            "per_mkt_mean": {m: (float(np.mean(v)) if v else None)
                             for m, v in per_mkt_rates.items()}}


def region_stat(masks: dict, outcomes: dict) -> dict:
    tc = th = 0
    per = {}
    for m in masks:
        c, h = clusters(masks[m], outcomes[m])
        tc += c
        th += h
        per[m] = {"clusters": c, "hits": h}
    return {"clusters": tc, "hits": th,
            "rate": (th / tc if tc else None), "per_market": per}


def run_region(masks: dict, outcomes: dict, perms: int, rng) -> dict:
    """Observed + null for one region (full / era / half). Region = same key-slices."""
    obs = region_stat(masks, outcomes)
    null = perm_null(masks, outcomes, perms, rng)
    nm = float(np.mean(null["pooled"]))
    out = {"observed": obs, "null_mean": nm,
           "p": (float(np.mean(null["pooled"] >= obs["rate"])) if obs["rate"] is not None
                 else None),
           "ratio": (obs["rate"] / nm if (obs["rate"] is not None and nm > 0) else None)}
    lb, ub = wilson(obs["hits"], obs["clusters"])
    out["wilson_lb"], out["wilson_ub"] = lb, ub
    out["per_market_ratio"] = {}
    for m in masks:
        pm, pmn = obs["per_market"][m], null["per_mkt_mean"].get(m)
        out["per_market_ratio"][m] = (
            (pm["hits"] / pm["clusters"]) / pmn
            if pm["clusters"] and pmn else None)
    return out


# ------------------------------------------------------------- market build --
def blend(legs: dict[str, pd.Series], weights: dict[str, float]) -> pd.Series:
    """Mirror composite_series' comp-leg blend + trailing percentile exactly."""
    num = den = None
    for k, ser in legs.items():
        w = weights[k]
        col = ser.fillna(0.5) * w
        av = ser.notna().astype(float) * w
        num = col if num is None else num + col
        den = av if den is None else den + av
    return pct_rank_window((num / den.replace(0, np.nan)).dropna(), _PCT_WIN)


def gated_states(comp: pd.Series, gate: pd.Series) -> pd.Series:
    score = comp * 100.0
    states = score.apply(lambda v: _band(v, _BANDS))
    g = gate.reindex(score.index).fillna(False)
    cap = ~g & states.isin(["elevated", "risk-off"])
    return states.where(~cap, "caution")


def episodes_rb(close: pd.Series) -> list[dict]:
    """R-B: onset = first close <= 0.98*max(close[t-63..t-1]) whose forward min over
    [t..t+21] <= 0.92*the same reference high; suppressed until 21 sessions pass or a new
    63d high prints."""
    px = close.values
    n = len(px)
    ref = pd.Series(px).rolling(63).max().shift(1).values      # max over [t-63, t-1]
    fwd_min = pd.Series(px[::-1]).rolling(22, min_periods=1).min().values[::-1]  # [t, t+21]
    eps, last_onset = [], None
    for t in range(63, n - 21):
        if not np.isfinite(ref[t]):
            continue
        if px[t] > ref[t] and last_onset is not None:
            last_onset = None                                  # new 63-session high re-arms
        if last_onset is not None and t - last_onset < 21:
            continue
        if px[t] <= 0.98 * ref[t] and fwd_min[t] <= 0.92 * ref[t]:
            eps.append({"onset": t})
            last_onset = t
    return eps


def build_market(key: str) -> dict | None:
    p = PROFILES[key]
    B, sub, comp, gate = composite_series(p)
    if comp is None:
        return None
    idx = B.index
    # comp legs from sub (the same construction compute() uses)
    legs, weights = {}, {}
    for comp_key, sub_codes, w in p.comp_legs:
        members = [sub[c] for c in sub_codes if c in sub]
        if members:
            legs[comp_key] = pd.concat(members, axis=1, sort=False).mean(axis=1)
            weights[comp_key] = w
    # substrate self-check: our blend must reproduce the engine composite
    check = blend(legs, weights)
    common = comp.index.intersection(check.index)
    assert np.allclose(comp.loc[common].values, check.loc[common].values,
                       atol=1e-12, equal_nan=True), \
        f"{key}: blend mirror diverges from composite_series"

    states_inc = gated_states(comp, gate)
    uidx = states_inc.index                                   # analysis dates (post-warmup)
    close = B.reindex(uidx).ffill()
    # outcome: audit-grammar — min of the NEXT 21 closes vs the as-of close
    fwd = pd.Series(close.values[::-1]).rolling(H21, min_periods=H21).min().values[::-1]
    fwd_min_next = np.roll(fwd, -1)                            # min over [t+1, t+21]
    mature = np.arange(len(uidx)) < (len(uidx) - H21)
    hit = np.where(mature, (fwd_min_next / close.values - 1.0) <= DD, False)

    g = gate.reindex(uidx).fillna(False).values
    loud_inc = states_inc.isin(["elevated", "risk-off"]).values
    legs_u = {k: v.reindex(uidx).values for k, v in legs.items()}

    # --- S2 substrate: stitched fx raw series (mirror _sub_legs), two-sided percentile
    pair = _read(*p.fx_pair)
    fx = pair.reindex(idx).ffill().pct_change(21) * p.fx_risk_sign if pair is not None else None
    dxy = _read("yahoo", "DX-Y.NYB")
    if dxy is not None:
        d = dxy.reindex(idx).ffill().pct_change(63)
        fx = d if fx is None else fx.combine_first(d)
    one = pct_rank_window(fx.dropna(), _PCT_WIN)
    stitched_ok = bool(np.allclose(one.reindex(uidx).dropna().values,
                                   sub[p.fx_code].reindex(uidx).dropna().values, atol=1e-12))
    two = pct_rank_window(fx.abs().dropna(), _PCT_WIN)
    gate_full = gate.reindex(idx).fillna(False)
    one_f, two_f = one.reindex(idx), two.reindex(idx)
    legv2_gc = one_f.where(~gate_full, pd.concat([one_f, two_f], axis=1, sort=False).max(axis=1))
    legv2_al = pd.concat([one_f, two_f], axis=1, sort=False).max(axis=1)
    comp_v2 = {}
    for tag, leg in (("gc", legv2_gc), ("always", legv2_al)):
        lv = dict(legs)
        lv["fx"] = leg
        comp_v2[tag] = gated_states(blend(lv, weights), gate)

    # --- S3 substrate: velocity legs + v3 composites
    vel = {w: pct_rank_window((-B.pct_change(w)).dropna(), _PCT_WIN) for w in (10, 21)}
    comp_v3 = {}
    for w in (10, 21):
        lv = dict(legs)
        lv["velocity"] = vel[w].reindex(idx)
        wv = dict(weights)
        wv["velocity"] = 0.6
        comp_v3[w] = gated_states(blend(lv, wv), gate)

    return {"key": key, "uidx": uidx, "close": close, "hit": hit, "gate": g,
            "loud_inc": loud_inc, "legs": legs_u, "states_inc": states_inc,
            "stitched_ok": stitched_ok,
            "vel": {w: vel[w].reindex(uidx).values for w in vel},
            "loud_v2": {t: comp_v2[t].reindex(uidx).isin(["elevated", "risk-off"])
                        .fillna(False).values for t in comp_v2},
            "loud_v3": {w: comp_v3[w].reindex(uidx).isin(["elevated", "risk-off"])
                        .fillna(False).values for w in comp_v3},
            "episodes": episodes_rb(close),
            "spearman_vel_ext": (float(pd.Series(vel[10].reindex(uidx).values)
                                       .corr(pd.Series(legs_u.get("extension")),
                                             method="spearman"))
                                 if legs_u.get("extension") is not None else None)}


# ------------------------------------------------------------------- gates ---
def regions_for(mkts: dict, mask_of) -> dict:
    """Build {region: (masks, outcomes)} for full / eras / halves. mask_of(M) -> bool arr."""
    out = {}
    for region in ("full", "pre2016", "post2016", "half1", "half2"):
        masks, outs = {}, {}
        for k, M in mkts.items():
            mask = mask_of(M) & (np.arange(len(M["uidx"])) < len(M["uidx"]) - H21)
            dates = M["uidx"]
            if region == "pre2016":
                sel = dates < ERA_SPLIT
            elif region == "post2016":
                sel = dates >= ERA_SPLIT
            elif region == "half1":
                sel = np.arange(len(dates)) < len(dates) // 2
            elif region == "half2":
                sel = np.arange(len(dates)) >= len(dates) // 2
            else:
                sel = np.ones(len(dates), bool)
            sel = np.asarray(sel)
            masks[k], outs[k] = mask[sel], M["hit"][sel]
        out[region] = (masks, outs)
    return out


def added_days_budget(mkts: dict, added_of, pooled_cap: float, mkt_cap: float) -> dict:
    tot_add = tot_days = 0
    per, ok = {}, True
    for k, M in mkts.items():
        dates = M["uidx"]
        y10 = dates >= (dates[-1] - pd.DateOffset(years=10))
        add = float(added_of(M)[np.asarray(y10)].mean()) * 100
        per[k] = round(add, 2)
        tot_add += added_of(M)[np.asarray(y10)].sum()
        tot_days += int(np.asarray(y10).sum())
        if add > mkt_cap:
            ok = False
    pooled = 100.0 * tot_add / tot_days
    return {"pooled_pp": round(pooled, 2), "per_market_pp": per,
            "pass": bool(ok and pooled <= pooled_cap),
            "caps": {"pooled": pooled_cap, "per_market": mkt_cap}}


def cell_verdict(cell: dict) -> str:
    g = cell["gates"]
    if g.get("kill"):
        return "KILL"
    if not g.get("budget", True):
        return "NO-GO"
    hard = (g.get("bh") and g.get("p_floor") and g.get("lift") and g.get("era") == "pass"
            and g.get("split") == "pass" and g.get("breadth") and g.get("n_floor"))
    extra = all(v for kk, v in g.items() if kk.startswith("extra_"))
    # S2 §5: a do-no-harm failure is a hard NO-GO veto (even in the ACCRUE zone).
    # S3 §2: a redundancy-gate failure only CAPS at ACCRUE — it is excluded from the veto.
    veto = not all(v for kk, v in g.items()
                   if kk.startswith("extra_") and kk != "extra_redundancy")
    if hard and extra and not g.get("cap_accrue"):
        return "GO"
    ratio = cell["full"].get("ratio")
    if ratio is not None and ratio > 1.0 and not veto:
        underpowered = (not g.get("n_floor")) or bool(g.get("cap_accrue")) or (
            not g.get("lift") and cell["full"]["wilson_lb"] >= cell["full"]["null_mean"])
        if underpowered or hard:
            return "ACCRUE"
    return "NO-GO"


def eval_cell(name: str, mkts: dict, mask_of, perms: int, rng, budget: dict | None,
              n_floor: int = N_FLOOR) -> dict:
    regs = regions_for(mkts, mask_of)
    res = {"cell": name}
    for rname, (masks, outs) in regs.items():
        res[rname if rname == "full" else rname] = run_region(masks, outs, perms, rng)
    full = res["full"]
    gates = {
        "n_floor": full["observed"]["clusters"] >= n_floor,
        "lift": (full["wilson_lb"] >= LIFT_MIN * full["null_mean"]
                 if full["null_mean"] else False),
        "p_floor": (full["p"] is not None and full["p"] < P_FLOOR),
        "kill": (full["wilson_ub"] < full["null_mean"] if full["null_mean"] else False),
    }
    era_c = [res["pre2016"]["observed"]["clusters"], res["post2016"]["observed"]["clusters"]]
    if min(era_c) < ERA_FLOOR:
        gates["era"] = "sparse"
        gates["cap_accrue"] = True
    else:
        gates["era"] = ("pass" if all((res[r]["ratio"] or 0) > 1.0
                                      for r in ("pre2016", "post2016")) else "fail")
    half_c = [res["half1"]["observed"]["clusters"], res["half2"]["observed"]["clusters"]]
    if min(half_c) < ERA_FLOOR:
        gates["split"] = "sparse"
        gates["cap_accrue"] = True
    else:
        gates["split"] = ("pass" if all((res[r]["ratio"] or 0) > 1.0
                                        for r in ("half1", "half2")) else "fail")
    pm = full["per_market_ratio"]
    gates["breadth"] = sum(1 for v in pm.values() if v is not None and v > 1.0) >= 5
    if budget is not None:
        gates["budget"] = budget["pass"]
        res["fp_budget"] = budget
    res["gates"] = gates
    return res


# --------------------------------------------------------------------- main --
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--perms", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=20260717)
    ap.add_argument("--out", default="data/risk_radar_intl/rri_study_results.json")
    args = ap.parse_args()
    rng = np.random.default_rng(args.seed)

    mkts = {}
    for k in MARKETS:
        M = build_market(k)
        if M is None:
            raise SystemExit(f"no data for {k}")
        assert M["stitched_ok"], f"{k}: fx stitch mirror diverges from engine sub-leg"
        mkts[k] = M

    P = args.perms
    cells = {}

    # --- S1 cells 1-4 ---------------------------------------------------------
    def s1_mask(thr, exfx):
        def f(M):
            names = [n for n in M["legs"] if not (exfx and n == "rateshock")]
            anyleg = np.zeros(len(M["uidx"]), bool)
            for n in names:
                v = M["legs"][n]
                anyleg |= np.nan_to_num(v, nan=0.0) >= thr
            return anyleg & M["gate"] & ~M["loud_inc"]
        return f

    for name, thr, exfx in (("s1_any88", 0.88, False), ("s1_exfx88", 0.88, True),
                            ("s1_any95", 0.95, False), ("s1_exfx95", 0.95, True)):
        mf = s1_mask(thr, exfx)
        budget = added_days_budget(mkts, mf, pooled_cap=12.0, mkt_cap=16.0)
        cell = eval_cell(name, mkts, mf, P, rng, budget)
        # S1 §3 secondary (reported, never gated): paired R-B episode capture + latency
        # under the floored states S_v1 = incumbent-loud OR trigger vs the incumbent
        cap_inc = cap_v1 = only_v1 = only_inc = 0
        lat_diffs = []
        for k, M in mkts.items():
            loud_v1 = M["loud_inc"] | mf(M)
            for ep in M["episodes"]:
                o = ep["onset"]
                wsl = slice(max(0, o - 10), min(len(M["uidx"]), o + 16))
                base = max(0, o - 10)
                ci, cv = bool(M["loud_inc"][wsl].any()), bool(loud_v1[wsl].any())
                cap_inc += ci
                cap_v1 += cv
                only_v1 += cv and not ci
                only_inc += ci and not cv
                def lat(states):
                    pos = np.flatnonzero(states[wsl])
                    return int(pos[0] + base - o) if pos.size else 15
                lat_diffs.append(lat(loud_v1) - lat(M["loud_inc"]))
        cell["s1_episode_receipt"] = {
            "capture": {"incumbent": cap_inc, "floored": cap_v1,
                        "floored_only": only_v1, "incumbent_only": only_inc},
            "latency_median_diff": float(np.median(lat_diffs)) if lat_diffs else None}
        cells[name] = cell

    # --- S2 cells 5-6 ---------------------------------------------------------
    for name, tag in (("s2_gate_conditional", "gc"), ("s2_always", "always")):
        def gained(M, tag=tag):
            return M["loud_v2"][tag] & ~M["loud_inc"]
        budget = added_days_budget(mkts, gained, pooled_cap=4.0, mkt_cap=6.0)
        cell = eval_cell(name, mkts, gained, P, rng, budget)
        # do-no-harm 1: lost vs gained cluster hit rates + episode capture
        lost_stat = region_stat({k: (mkts[k]["loud_inc"] & ~mkts[k]["loud_v2"][tag]
                                     & (np.arange(len(mkts[k]["uidx"]))
                                        < len(mkts[k]["uidx"]) - H21))
                                 for k in mkts}, {k: mkts[k]["hit"] for k in mkts})
        gained_rate = cell["full"]["observed"]["rate"] or 0.0
        lost_rate = lost_stat["rate"] or 0.0
        cap_inc = cap_v2 = 0
        de_lat_inc, de_lat_v2 = [], []
        for k, M in mkts.items():
            loud_v = M["loud_v2"][tag]
            for ep in M["episodes"]:
                o = ep["onset"]
                w = slice(max(0, o - 10), min(len(M["uidx"]), o + 16))
                cap_inc += bool(M["loud_inc"][w].any())
                cap_v2 += bool(loud_v[w].any())
                seg = M["close"].values[o:o + 64]
                tr = o + int(np.argmin(seg))
                for states, out in ((M["loud_inc"], de_lat_inc), (loud_v, de_lat_v2)):
                    below = np.flatnonzero(~states[tr:tr + 64])
                    out.append(int(below[0]) if below.size else 63)
        cell["do_no_harm"] = {
            "lost": lost_stat, "lost_rate": round(lost_rate, 4),
            "gained_rate": round(gained_rate, 4),
            "episode_capture": {"incumbent": cap_inc, "variant": cap_v2},
            "deescalation_median": {"incumbent": float(np.median(de_lat_inc)) if de_lat_inc else None,
                                    "variant": float(np.median(de_lat_v2)) if de_lat_v2 else None},
        }
        cell["gates"]["extra_lost_le_gained"] = lost_rate <= gained_rate
        cell["gates"]["extra_capture"] = cap_v2 >= cap_inc
        cell["gates"]["extra_deescalation"] = (
            de_lat_v2 and de_lat_inc and
            float(np.median(de_lat_v2)) - float(np.median(de_lat_inc)) <= 5.0)
        cells[name] = cell

    # --- S3 cells 7-8 ---------------------------------------------------------
    for name, w in (("s3_ret10", 10), ("s3_ret21", 21)):
        def trig(M, w=w):
            return (np.nan_to_num(M["vel"][w], nan=0.0) >= 0.95) & M["gate"] & ~M["loud_inc"]
        def added(M, w=w):
            return M["loud_v3"][w] & ~M["loud_inc"]
        budget = added_days_budget(mkts, added, pooled_cap=8.0, mkt_cap=10.0)
        cell = eval_cell(name, mkts, trig, P, rng, budget)
        # redundancy gate: sub-sample where extension leg < 0.88 (own null)
        sub_masks = {k: (trig(mkts[k])
                         & (np.nan_to_num(mkts[k]["legs"].get("extension"), nan=1.0) < 0.88)
                         & (np.arange(len(mkts[k]["uidx"])) < len(mkts[k]["uidx"]) - H21))
                     for k in mkts}
        sub = run_region(sub_masks, {k: mkts[k]["hit"] for k in mkts}, P, rng)
        cell["redundancy"] = sub
        if sub["observed"]["clusters"] < 5:
            cell["gates"]["cap_accrue"] = True
            cell["gates"]["extra_redundancy"] = True     # sparse: caps, doesn't fail
            cell["redundancy"]["status"] = "ERA-SPARSE"
        else:
            cell["gates"]["extra_redundancy"] = bool(
                (sub["ratio"] or 0) > 1.0 and sub["wilson_lb"] >= 1.10 * sub["null_mean"])
        # H2 latency (Stage-B gate, not family FDR)
        diffs, mkt_dir = [], {}
        for k, M in mkts.items():
            dd = []
            for ep in M["episodes"]:
                o = ep["onset"]
                wsl = slice(max(0, o - 10), min(len(M["uidx"]), o + 16))
                base = max(0, o - 10)
                def lat(states):
                    pos = np.flatnonzero(states[wsl])
                    return int(pos[0] + base - o) if pos.size else 15
                dd.append(lat(M["loud_v3"][w]) - lat(M["loud_inc"]))
            if len(dd) >= 3:
                mkt_dir[k] = float(np.median(dd))
            diffs.extend(dd)
        h2 = {"median_diff": float(np.median(diffs)) if diffs else None,
              "per_market_median": mkt_dir,
              "n_episodes": len(diffs)}
        h2["pass"] = bool(diffs and h2["median_diff"] <= -2.0
                          and sum(1 for v in mkt_dir.values() if v < 0) >= 5)
        cell["h2_latency"] = h2
        # whipsaw receipt (printed, not gated): share of trigger clusters whose market closed
        # ABOVE the first trigger day's close at +21 sessions, per era
        ws = {"pre2016": [0, 0], "post2016": [0, 0]}
        for k, M in mkts.items():
            mask = trig(M) & (np.arange(len(M["uidx"])) < len(M["uidx"]) - H21)
            pos = np.flatnonzero(mask)
            if pos.size == 0:
                continue
            starts = pos[np.flatnonzero(np.concatenate(([True], np.diff(pos) >= GAP)))]
            cl = M["close"].values
            for t0 in starts:
                era = "pre2016" if M["uidx"][t0] < ERA_SPLIT else "post2016"
                ws[era][0] += 1
                ws[era][1] += int(cl[t0 + H21] > cl[t0])
        cell["whipsaw_receipt"] = {e: {"clusters": n, "closed_above_at_h21": a,
                                       "share": (round(a / n, 3) if n else None)}
                                   for e, (n, a) in ws.items()}
        cells[name] = cell

    # --- family BH-FDR (8 cells, step-up) --------------------------------------
    order = ["s1_any88", "s1_exfx88", "s1_any95", "s1_exfx95",
             "s2_gate_conditional", "s2_always", "s3_ret10", "s3_ret21"]
    ps = [(c, cells[c]["full"]["p"]) for c in order]
    ranked = sorted(ps, key=lambda t: (t[1] is None, t[1]))
    m = len(ranked)
    kmax = 0
    for i, (c, p) in enumerate(ranked, 1):
        if p is not None and p <= (i / m) * FAMILY_ALPHA:
            kmax = i
    for i, (c, p) in enumerate(ranked, 1):
        cells[c]["gates"]["bh"] = bool(i <= kmax)
        cells[c]["bh_rank"] = i

    for c in order:
        cells[c]["verdict"] = cell_verdict(cells[c])
        # S3 promotion nuance: H1 GO but H2 fail -> NO-GO for promotion (parks)
        if c.startswith("s3") and cells[c]["verdict"] == "GO" \
                and not cells[c]["h2_latency"]["pass"]:
            cells[c]["verdict"] = "NO-GO"
            cells[c]["verdict_note"] = "H1 passed but H2 latency failed — parks as confluence receipt (prereg S3 §6)"

    # ---------------------------------------------------------------- output --
    def clean(o):
        if isinstance(o, dict):
            return {k: clean(v) for k, v in o.items() if k not in ("uidx",)}
        if isinstance(o, (np.bool_, bool)):
            return bool(o)
        if isinstance(o, (np.floating, float)):
            return round(float(o), 5)
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, np.ndarray):
            return None
        if isinstance(o, list):
            return [clean(v) for v in o]
        return o

    result = {
        "schema": "rri_stage_a.v1",
        "family": "rri_2026h2",
        "prereg": "research/RRI_CRASH_ANTIFIRE_PROGRAM.md (+S1..S3) — PR #2725, ratified 2026-07-17",
        "perms": P, "seed": args.seed,
        "data_asof": {k: str(mkts[k]["uidx"][-1].date()) for k in mkts},
        "spearman_vel_ext": {k: mkts[k]["spearman_vel_ext"] for k in mkts},
        "episodes_rb": {k: len(mkts[k]["episodes"]) for k in mkts},
        "cells": {c: clean(cells[c]) for c in order},
        "verdicts": {c: cells[c]["verdict"] for c in order},
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1, default=str))

    print(f"RRI Stage-A — perms={P} seed={args.seed}")
    for c in order:
        f = cells[c]["full"]
        g = cells[c]["gates"]
        print(f"  {c:22s} clusters={f['observed']['clusters']:4d} hits={f['observed']['hits']:4d} "
              f"rate={f['observed']['rate'] if f['observed']['rate'] is not None else float('nan'):.3f} "
              f"null={f['null_mean']:.3f} ratio={(f['ratio'] or 0):.2f} "
              f"LB={f['wilson_lb']:.3f} p={f['p']:.4f} bh={g['bh']} era={g['era']} "
              f"split={g['split']} breadth={g['breadth']} budget={g.get('budget')} "
              f"-> {cells[c]['verdict']}")
    print(f"written: {out}")


if __name__ == "__main__":
    main()
