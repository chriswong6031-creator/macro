"""Arm P, FAITHFUL: the packet's own isolation via sq.analyze() on/off, graded on the
repaired ruler. Distinct from reclaim_veto.py's Arm P, which applied _buy_filter to the
Terminal ORACLE frame; Prophet builds its own signal_frame, so the two cohorts differ."""
from __future__ import annotations
import json, multiprocessing as mp, os, sys
from collections import Counter
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, "/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/regime-blocked-entry-signals-055e2c")
import study as S, r3_axes as R3                       # noqa: E402
from engine import signal_quality as sq                # noqa: E402

OUT = Path(__file__).resolve().parents[3]
BLOCK_REASON, TAKE = sq.CT_RECLAIM_FAIL, "take"


def anchors(close: pd.Series) -> dict:
    sig = sq.signal_frame(close)
    if sig.empty:
        return {}
    sig = sig.dropna(subset=["macd", "sig", "k", "d", "rsi14"])
    sidx = sig.index
    bin_last = pd.Series(close.index, index=close.index).resample("3B").last().dropna()
    out = {}
    for i in range(len(sidx) - 2):
        d = bin_last.get(sidx[i + 2])
        if d is not None and pd.notna(d):
            out[sidx[i]] = pd.Timestamp(d)
    return out


def _w(sym: str):
    try:
        df = S.load_ohlc(sym)
        if df is None:
            return []
        c = df["close"].dropna()
        on, off = sq.analyze(sym, c, reclaim_veto=True), sq.analyze(sym, c, reclaim_veto=False)
        if not on or not off:
            return []
    except Exception:
        return []
    offm = {m.get("date"): m for m in off["markers"]}
    refs = [m["date"] for m in on["markers"]
            if m.get("quality") == "block" and m.get("reason") == BLOCK_REASON
            and offm.get(m.get("date"), {}).get("quality") == TAKE]
    if not refs:
        return []
    anc = anchors(c)
    idx = df.index
    close = df["close"].to_numpy(float); high = df["high"].to_numpy(float)
    low = df["low"].to_numpy(float); opn = df["open"].to_numpy(float)
    atr = S.wilder_atr(high, low, close)
    out = []
    for ds in refs:
        d = pd.Timestamp(ds); a = anc.get(d)
        if a is None:
            continue
        kp = int(idx.searchsorted(a))
        if kp >= len(idx):
            continue
        ei = kp + 1
        if ei >= len(idx):
            continue
        base = float(np.nanmin(low[max(0, kp - 8):kp + 1]))   # 9-session (3x3D) washout low
        av = float(atr[kp])
        if not np.isfinite(av) or av <= 0 or not np.isfinite(base):
            continue
        po = opn[ei]
        entry = float(po) if (np.isfinite(po) and po > 0) else float(close[ei])
        stop = base - 0.5 * av
        if entry - stop <= 0 or (entry - stop) / entry < 0.005:
            continue
        graded = ei < len(idx) - 21
        sim = S.sim_exits(ei, entry, stop, close, high, low, opn) if graded else None
        out.append({"sym": sym, "refusal_date": str(d.date()), "known_ts": str(a.date()),
                    "entry_date": str(idx[ei].date()), "entry_px": entry, "graded": graded,
                    "R": sim["d_R"] if sim else None, "ret": sim["d_ret"] if sim else None,
                    "cens": (sim["d_reason"] == "censored") if sim else False})
    return out


def main() -> int:
    prod = Path(os.environ["PROD_BARS"])
    us = sorted(p.stem for p in prod.glob("*.json") if not p.stem.endswith((".HK", ".SS", ".SZ")))
    with mp.Pool(20) as pool:
        chunks = pool.map(_w, us, chunksize=8)
    ev = pd.DataFrame([r for c in chunks for r in c])
    print(f"[armP faithful] refusals={len(ev)} names={ev.sym.nunique()} gradable={int(ev.graded.sum())}", flush=True)
    ev["era"] = np.where(ev["entry_date"] <= S.DESIGN_END, "design", "verdict")
    ev["_kt"] = pd.DatetimeIndex(ev["known_ts"]).values.astype("datetime64[D]").astype("int32")

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
    bg = {b: [t for t in members.get(b, []) if t in dd] for b in set(basket.values())}
    sg: dict = {}
    for t, s2 in sector.items():
        if t in dd:
            sg.setdefault(s2, []).append(t)
    peer = np.full(len(ev), np.nan); src = np.array(["none"] * len(ev), dtype=object)
    for gmap, groups, tag in ((basket, bg, "basket"), (sector, sg, "sector")):
        assign = ev["sym"].map(gmap)
        for g, mem in groups.items():
            if len(mem) < 5:
                continue
            D = pd.DataFrame({m: pd.Series(dd[m][1], index=dd[m][0]) for m in mem}).sort_index()
            iv, vals = D.index.to_numpy(), D.to_numpy("float32")
            cols = {c2: k for k, c2 in enumerate(D.columns)}
            sel = np.flatnonzero((assign == g).to_numpy() & ~np.isfinite(peer))
            if not sel.size:
                continue
            pos = np.searchsorted(iv, ev["_kt"].to_numpy()[sel], side="right") - 1
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

    g = ev[ev.graded & ev.peer_dd.notna()]
    hd = g[g.era == "verdict"].copy(); des = g[g.era == "design"]
    cov = {"fire_weighted_union": float(ev[ev.graded]["peer_dd"].notna().mean()),
           "fire_weighted_basket": float((ev[ev.graded]["peer_src"] == "basket").mean()),
           "n_heldout": int(len(hd)), "n_design": int(len(des))}
    cov["passes_floor"] = cov["fire_weighted_union"] >= 0.60
    grid = {}
    for th in R3.GRID:
        cell = R3.episodes_and_clusters(hd[hd.peer_dd <= -th].copy(), cal)
        comp = R3.episodes_and_clusters(hd[hd.peer_dd > -th].copy(), cal)
        dc, dk = des[des.peer_dd <= -th], des[des.peer_dd > -th]
        sep = (abs(dc["R"].clip(upper=R3.CAP).mean() - dk["R"].clip(upper=R3.CAP).mean())
               if len(dc) and len(dk) else None)
        gg = {"design_abs_separation": None if sep is None else float(sep),
              "cell_level": R3.agg(cell), "complement_level": R3.agg(comp),
              "cell_boot_cluster": R3.boot(cell, "cluster"),
              "cell_boot_episode": R3.boot(cell, "episode"),
              "cell_equal_date": R3.equal_date(cell),
              "diff_vs_complement": R3.diff_boot(cell, comp), "loco_loo": R3.loco_loo(cell)}
        ck = {"G1_cluster": (gg["cell_boot_cluster"].get("ci_lo") or -1) > 0,
              "G2_diff": (gg["diff_vs_complement"].get("ci_lo") or -1) > 0,
              "G3_eqdate": (gg["cell_equal_date"].get("ci_lo") or -1) > 0,
              "G4_episode": (gg["cell_boot_episode"].get("ci_lo") or -1) > 0,
              "G5_excovid": (gg["loco_loo"].get("ex_covid") or -1) > 0,
              "G6_loomin": (gg["loco_loo"].get("loo_episode_min") or -1) > 0,
              "G7_floor": cov["passes_floor"],
              "G8_not_thin": (gg["loco_loo"].get("n_episodes") or 0) >= 5}
        gg["checks"] = ck; gg["verdict"] = "PASS" if all(ck.values()) else "FAIL"
        grid[f"{th:.2f}"] = gg
    nem = ev[ev.sym == "NEM"].tail(4).to_dict("records")
    res = {"coverage": cov, "grid": grid, "n_refusals": int(len(ev)),
           "n_names": int(ev.sym.nunique()), "nem_last_refusals": nem,
           "note": "Arm P via packet path sq.analyze(on/off); BLOCK_REASON bound to CT_RECLAIM_FAIL"}
    (OUT / "arm_p_faithful.json").write_text(json.dumps(res, indent=1, default=str))
    ev.drop(columns=["_kt"]).to_parquet(OUT / "arm_p_faithful_events.parquet")
    print(f"\n{'thr':>5}{'capR':>8}{'clusCI':>16}{'epiCI':>16}{'eqdate':>8}{'diff':>8}"
          f"{'exCOVID':>9}{'LOOmin':>8}{'fires':>7}{'epis':>6}  verdict")
    for th, gg in grid.items():
        L, cb, eb = gg["cell_level"], gg["cell_boot_cluster"], gg["cell_boot_episode"]
        ed, dfc, ll = gg["cell_equal_date"], gg["diff_vs_complement"], gg["loco_loo"]
        if not L.get("n"):
            print(f"{th:>5}  (empty)"); continue
        print(f"{th:>5}{L['mean_R_capped10']:>8.3f}[{cb.get('ci_lo',0):>6.3f},{cb.get('ci_hi',0):>6.3f}]"
              f"[{eb.get('ci_lo',0):>6.3f},{eb.get('ci_hi',0):>6.3f}]{(ed.get('point') or 0):>8.3f}"
              f"{(dfc.get('point') or 0):>8.3f}{(ll.get('ex_covid') or float('nan')):>9.3f}"
              f"{(ll.get('loo_episode_min') or float('nan')):>8.3f}{L['n']:>7}"
              f"{(ll.get('n_episodes') or 0):>6}  {gg['verdict']}")
    print(f"coverage {cov}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
