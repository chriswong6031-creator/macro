"""RECLAIM-VETO CONDITIONAL — Arm T (Terminal keeper) + Arm P (Prophet signal_quality).

Prereg: research/RECLAIM_VETO_CONDITIONAL_PREREG.md (frozen 2026-08-10, branch
claude/reclaim-veto-prereg-055e2c). Inherits the repaired blocked-entry machinery: m FIXED 0.5,
intrabar fills PRIMARY, +10R cap, censored-unstopped excluded, equal-notional beside every R read,
clustering = episode x name AND episode, ex-COVID + LOO-episode required.

DATA BASIS: PRODUCTION bars (regrade/prod_bars, run to IPO). CN/HK excluded per §1.

Both arms are driven off ONE replay of the production signal frame:
  Arm T = confluence_v2.keeper_quality_map verdict 'block' with a CT reclaim reason
          ("failed reclaim-and-hold" / "counter-trend, no 200-reclaim/hold");
          "veto: bearish divergence" blocks EXCLUDED and counted.
  Arm P = macro engine.signal_quality._buy_filter called TWICE on the same bar
          (reclaim_veto=True/False); refused = on is False with reason in
          {CT_RECLAIM_FAIL, CT_BOTH_FAIL} AND off is True  (the packet's isolation).
Both arms additionally carry a RELIEVABLE flag = the veto-off path actually takes the fire,
because the prereg's Arm-T reason set is not co-extensive with what waiving the leg can relieve
(see REPORT §flaws).
"""
from __future__ import annotations

import json
import multiprocessing as mp
import os
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SHARED_STUDY = ROOT / "research" / "blocked_entry_study"
sys.path[:0] = [str(ROOT), str(SHARED_STUDY)]

import study as S                      # noqa: E402  (regrade build: OHLC_BASIS switch)
import r3_axes as R3                   # noqa: E402  (peers, episodes, agg, boot, loco)
from signal_layer import confluence as oracle              # noqa: E402
from signal_layer.confluence_v2 import keeper_quality_map  # noqa: E402
from engine.signal_quality import (                        # noqa: E402
    _buy_filter, CT_RECLAIM_FAIL, CT_BOTH_FAIL)

OUT = Path(__file__).resolve().parent
GRID = R3.GRID
CAP, B, SEED = R3.CAP, R3.B, R3.SEED
DIV_REASON = "veto: bearish divergence"
T_REASONS = ("failed reclaim-and-hold", "counter-trend, no 200-reclaim/hold")
P_REASONS = (CT_RECLAIM_FAIL, CT_BOTH_FAIL)
CITED = {"HL": ["2026-06-16", "2026-06-25"], "NEM": ["2026-08-05"]}


def _worker(sym: str):
    """Both arms for one name, off a single production-bar replay."""
    try:
        df = S.load_ohlc(sym)
    except Exception:
        return []
    if df is None:
        return []
    dc = df["close"]
    try:
        sig = oracle.compute_signals(dc)
    except Exception:
        return []
    if sig.empty:
        return []
    rows = sig.dropna(subset=["macd", "sig", "k", "d", "rsi14"])
    n = len(rows)
    if n < 40:
        return []
    rr = rows.reset_index(drop=True)

    close = df["close"].to_numpy(float); high = df["high"].to_numpy(float)
    low = df["low"].to_numpy(float); opn = df["open"].to_numpy(float)
    atr = S.wilder_atr(high, low, close)
    didx = df.index
    od, cd, _ = oracle._3d_groups(dc, 0)
    bo = didx.searchsorted(od); bc = didx.searchsorted(cd)
    pos_of = {ts: j for j, ts in enumerate(od)}
    known = pd.DatetimeIndex(rows["known_ts"])

    # ---- Arm T: keeper verdicts on raw buys that PASSED bear_block ---------
    km = keeper_quality_map(sig)
    # ---- Arm P: the production buy-filter called twice on the same bars ----
    from signal_layer.confluence_v2 import _bearish_divergence, _swing_highs
    hi = _swing_highs(rr["close"])
    raw_pass = ((rr["CB"] | rr["revBuy"]) & ~rr["bear_block"]).to_numpy()

    out = []
    for i in np.flatnonzero(raw_pass):
        i = int(i)
        j = pos_of.get(rows.index[i])
        if j is None or j < 2:
            continue
        kp = int(didx.searchsorted(known[i]))
        ei = kp + 1
        if ei >= len(didx) - 21:
            continue
        base = float(np.nanmin(low[bo[j - 2]:bc[j] + 1]))
        a = float(atr[kp])
        if not np.isfinite(a) or a <= 0 or not np.isfinite(base):
            continue
        po = opn[ei]
        entry = float(po) if (np.isfinite(po) and po > 0) else float(close[ei])
        stop = base - 0.5 * a
        if entry - stop <= 0 or (entry - stop) / entry < 0.005:
            continue
        sim = S.sim_exits(ei, entry, stop, close, high, low, opn)

        tv, tr = km.get(i, (None, None))
        bear = bool(_bearish_divergence(i, rr["close"], rr["macd"], hi))
        on = _buy_filter(i, rr, bear, n, reclaim_veto=True)
        off = _buy_filter(i, rr, bear, n, reclaim_veto=False)

        rec = {"sym": sym, "entry_date": str(didx[ei].date()),
               "known_ts": str(known[i].date()), "entry_px": entry,
               "R": sim["d_R"], "ret": sim["d_ret"], "cens": sim["d_reason"] == "censored",
               "R_close": sim["a_R"], "ret_close": sim["a_ret"],
               "keeper_verdict": tv, "keeper_reason": tr,
               "p_on_take": on[0], "p_on_reason": on[1],
               "p_off_take": off[0], "p_off_reason": off[1]}
        rec["armT"] = bool(tv == "block" and tr in T_REASONS)
        rec["armT_div_excluded"] = bool(tv == "block" and tr == DIV_REASON)
        # relievable = the keeper's own counter-trend leg would take it with the reclaim
        # requirement removed (the same off-path Arm P uses).
        rec["armT_relievable"] = bool(rec["armT"] and off[0] is True)
        rec["armP"] = bool(on[0] is False and on[1] in P_REASONS and off[0] is True)
        rec["armP_ct_reason_any"] = bool(on[0] is False and on[1] in P_REASONS)
        if rec["armT"] or rec["armP"] or rec["armT_div_excluded"] or rec["armP_ct_reason_any"]:
            out.append(rec)
    return out


def main() -> int:
    prod = Path(os.environ["PROD_BARS"])
    panel = sorted(p.stem for p in prod.glob("*.json"))
    us = [s for s in panel if not s.endswith((".HK", ".SS", ".SZ"))]
    n_excl = len(panel) - len(us)
    print(f"[panel] prod bars {len(panel)}; CN/HK excluded {n_excl}; US {len(us)}", flush=True)

    with mp.Pool(20) as pool:
        chunks = pool.map(_worker, us, chunksize=8)
    ev = pd.DataFrame([r for c in chunks for r in c])
    ev["era"] = np.where(ev["entry_date"] <= S.DESIGN_END, "design", "verdict")
    ev["_kt"] = pd.DatetimeIndex(ev["known_ts"]).values.astype("datetime64[D]").astype("int32")
    print(f"[cohorts] rows={len(ev)} armT={int(ev.armT.sum())} "
          f"(relievable {int(ev.armT_relievable.sum())}) armP={int(ev.armP.sum())} "
          f"div-excluded={int(ev.armT_div_excluded.sum())}", flush=True)

    # ---- basket/sector peer state (r3 machinery, production bars) ----------
    d = S.MACRO / "data"
    lp = ({p.stem for p in (d / "baskets" / "ohlcv").glob("*.parquet")}
          | {p.stem for p in (d / "stocks").glob("*.parquet")})
    basket, sector, members = R3.build_peer_maps(set(us) | lp)
    dd, day = {}, Counter()
    with mp.Pool(20) as pool:
        for res in pool.imap_unordered(R3._dd_worker, us, chunksize=16):
            if res is None:
                continue
            s2, days, v = res
            day.update(days.tolist()); dd[s2] = (days, v)
    cal = np.array(sorted(day))
    bgroups = {b: [t for t in members.get(b, []) if t in dd] for b in set(basket.values())}
    sgroups: dict = {}
    for t, s2 in sector.items():
        if t in dd:
            sgroups.setdefault(s2, []).append(t)

    peer = np.full(len(ev), np.nan); src = np.array(["none"] * len(ev), dtype=object)
    for gmap, groups, tag in ((basket, bgroups, "basket"), (sector, sgroups, "sector")):
        assign = ev["sym"].map(gmap)
        for g, mem in groups.items():
            if len(mem) < 5:
                continue
            D = pd.DataFrame({m: pd.Series(dd[m][1], index=dd[m][0]) for m in mem}).sort_index()
            idx_, vals = D.index.to_numpy(), D.to_numpy("float32")
            cols = {c2: k for k, c2 in enumerate(D.columns)}
            sel = np.flatnonzero((assign == g).to_numpy() & ~np.isfinite(peer))
            if not sel.size:
                continue
            pos = np.searchsorted(idx_, ev["_kt"].to_numpy()[sel], side="right") - 1
            for e_i, p in zip(sel, pos):
                if p < 0:
                    continue
                row = vals[p]; fin = np.isfinite(row)
                jj = cols.get(ev["sym"].iat[e_i])
                if jj is not None and fin[jj]:
                    fin = fin.copy(); fin[jj] = False
                if fin.any():
                    peer[e_i] = float(np.median(row[fin])); src[e_i] = tag
    ev["peer_dd"] = peer; ev["peer_src"] = src

    res: dict = {"meta": {"prereg": "RECLAIM_VETO_CONDITIONAL_PREREG.md",
                          "basis": "PRODUCTION bars (regrade/prod_bars)",
                          "n_prod_bars": len(panel), "n_us": len(us), "n_cnhk_excluded": n_excl,
                          "m": "0.5 fixed", "cap": CAP, "B": B, "seed": SEED,
                          "signal_sha256": S.SIGNAL_SOURCE_SHA256},
                 "cohorts": {}, "arms": {}, "exemplars": {}, "current_membership": {}}

    res["cohorts"] = {
        "armT_literal_prereg": int(ev.armT.sum()),
        "armT_relievable_by_waiver": int(ev.armT_relievable.sum()),
        "armT_bearish_div_excluded": int(ev.armT_div_excluded.sum()),
        "armT_reason_mix": Counter(ev.loc[ev.armT, "keeper_reason"]).most_common(),
        "armP_refused": int(ev.armP.sum()),
        "armP_ct_reason_any": int(ev.armP_ct_reason_any.sum()),
        "armP_reason_mix": Counter(ev.loc[ev.armP_ct_reason_any, "p_on_reason"]).most_common(),
    }

    for arm, mask in (("T", ev.armT), ("T_relievable", ev.armT_relievable), ("P", ev.armP)):
        sub = ev[mask & ev.peer_dd.notna()]
        hd = sub[sub.era == "verdict"].copy()
        des = sub[sub.era == "design"]
        cov = {"fire_weighted_union": float(ev[mask]["peer_dd"].notna().mean()),
               "fire_weighted_basket": float((ev[mask]["peer_src"] == "basket").mean()),
               "n_heldout": int(len(hd)), "n_design": int(len(des))}
        cov["passes_floor"] = cov["fire_weighted_union"] >= 0.60
        grid: dict = {}
        for th in GRID:
            cell = R3.episodes_and_clusters(hd[hd.peer_dd <= -th].copy(), cal)
            comp = R3.episodes_and_clusters(hd[hd.peer_dd > -th].copy(), cal)
            dc2, dk = des[des.peer_dd <= -th], des[des.peer_dd > -th]
            sep = (abs(dc2["R"].clip(upper=CAP).mean() - dk["R"].clip(upper=CAP).mean())
                   if len(dc2) and len(dk) else None)
            g = {"design_abs_separation": None if sep is None else float(sep),
                 "cell_level": R3.agg(cell), "complement_level": R3.agg(comp),
                 "cell_boot_cluster": R3.boot(cell, "cluster"),
                 "cell_boot_episode": R3.boot(cell, "episode"),
                 "cell_equal_date": R3.equal_date(cell),
                 "diff_vs_complement": R3.diff_boot(cell, comp),
                 "loco_loo": R3.loco_loo(cell),
                 "admit_share_heldout": float((hd.peer_dd <= -th).mean()) if len(hd) else None}
            ck = {"G1_cluster_CI_gt0": (g["cell_boot_cluster"].get("ci_lo") or -1) > 0,
                  "G2_diff_CI_gt0": (g["diff_vs_complement"].get("ci_lo") or -1) > 0,
                  "G3_equal_date_CI_gt0": (g["cell_equal_date"].get("ci_lo") or -1) > 0,
                  "G4_episode_CI_gt0": (g["cell_boot_episode"].get("ci_lo") or -1) > 0,
                  "G5_ex_covid_positive": (g["loco_loo"].get("ex_covid") or -1) > 0,
                  "G6_loo_min_positive": (g["loco_loo"].get("loo_episode_min") or -1) > 0,
                  "G7_coverage_floor": cov["passes_floor"],
                  "G8_not_episode_thin": (g["loco_loo"].get("n_episodes") or 0) >= 5}
            g["checks"] = ck
            g["verdict"] = "PASS" if all(ck.values()) else "FAIL"
            grid[f"{th:.2f}"] = g
        ok = [k for k in grid if grid[k]["design_abs_separation"] is not None]
        res["arms"][arm] = {"coverage": cov, "grid": grid,
                            "design_selected": (max(ok, key=lambda k: grid[k]["design_abs_separation"])
                                                if ok else None)}

    # ---- exemplar rows -----------------------------------------------------
    for sym, dates in CITED.items():
        for fd in dates:
            r = ev[(ev.sym == sym) & (ev.entry_date >= fd)].head(1)
            m = ev[(ev.sym == sym) & (ev.known_ts == fd)]
            row = m.iloc[0] if len(m) else (r.iloc[0] if len(r) else None)
            if row is None:
                res["exemplars"][f"{sym}@{fd}"] = {"found": False}
                continue
            res["exemplars"][f"{sym}@{fd}"] = {
                "found": True, "known_ts": row["known_ts"], "entry_date": row["entry_date"],
                "entry_px": round(float(row["entry_px"]), 4),
                "keeper": [row["keeper_verdict"], row["keeper_reason"]],
                "armT": bool(row["armT"]), "armT_relievable": bool(row["armT_relievable"]),
                "armP": bool(row["armP"]), "p_on": [row["p_on_take"], row["p_on_reason"]],
                "p_off": [row["p_off_take"], row["p_off_reason"]],
                "peer_src": row["peer_src"],
                "peer_dd": None if pd.isna(row["peer_dd"]) else round(float(row["peer_dd"]), 4),
                "admitted": {f"{th:.0%}": (bool(pd.notna(row["peer_dd"]) and row["peer_dd"] <= -th))
                             for th in GRID}}

    # ---- current membership ------------------------------------------------
    tape_k = int(cal.max())
    gnow = {}
    for tag, groups in (("basket", bgroups), ("sector", sgroups)):
        for g, mem in groups.items():
            mem = [m for m in mem if m in dd]
            if len(mem) < 5:
                continue
            D = pd.DataFrame({m: pd.Series(dd[m][1], index=dd[m][0]) for m in mem}).sort_index()
            p = int(np.searchsorted(D.index.to_numpy(), tape_k, side="right")) - 1
            if p < 0:
                continue
            row = D.to_numpy("float32")[p]; row = row[np.isfinite(row)]
            if row.size:
                gnow[f"{tag}:{g}"] = float(np.median(row))
    res["current_membership"] = {
        "as_of": str(pd.Timestamp(tape_k, unit="D").date()),
        "by_threshold": {f"{th:.0%}": sorted([g for g, v in gnow.items() if v <= -th])[:20]
                         for th in GRID},
        "deepest": dict(sorted(gnow.items(), key=lambda x: x[1])[:10])}

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "reclaim_veto_results.json").write_text(json.dumps(res, indent=1, default=str))
    ev.drop(columns=["_kt"]).to_parquet(OUT / "reclaim_veto_events.parquet")

    print(f"\n{'arm':14s}{'thr':>5}{'capR':>8}{'clusCI':>16}{'epiCI':>16}{'eqdate':>8}"
          f"{'diff':>8}{'exCOVID':>9}{'LOOmin':>8}{'fires':>7}{'epis':>6}  verdict")
    print("-" * 118)
    for arm in ("T", "T_relievable", "P"):
        for th, g in res["arms"][arm]["grid"].items():
            L, cb, eb = g["cell_level"], g["cell_boot_cluster"], g["cell_boot_episode"]
            ed, dfc, ll = g["cell_equal_date"], g["diff_vs_complement"], g["loco_loo"]
            if not L.get("n"):
                print(f"{arm:14s}{th:>5}  (empty cell)"); continue
            print(f"{arm:14s}{th:>5}{L['mean_R_capped10']:>8.3f}"
                  f"[{cb.get('ci_lo',0):>6.3f},{cb.get('ci_hi',0):>6.3f}]"
                  f"[{eb.get('ci_lo',0):>6.3f},{eb.get('ci_hi',0):>6.3f}]"
                  f"{(ed.get('point') or 0):>8.3f}{(dfc.get('point') or 0):>8.3f}"
                  f"{(ll.get('ex_covid') or float('nan')):>9.3f}"
                  f"{(ll.get('loo_episode_min') or float('nan')):>8.3f}"
                  f"{L['n']:>7}{(ll.get('n_episodes') or 0):>6}  {g['verdict']}")
    print(f"\n[cohorts] {json.dumps({k: v for k, v in res['cohorts'].items() if isinstance(v, int)})}")
    print(f"-> {OUT/'reclaim_veto_results.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
