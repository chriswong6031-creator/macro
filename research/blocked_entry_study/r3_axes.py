"""ROUND 3 — A1b thematic-basket peer set + measured dead arm (prereg §7 AMENDMENT 2).

Runs on the COMMITTED instrument (study.py @2ad6db7712b lineage, confluence.py sha-pinned) via a
shim; no repo file is modified.

§7 round-3 methodology, all mandatory and implemented here:
  m FIXED 0.5 (F6)                        · primary aggregate = mean R CAPPED at +10R, winsor-99
  censored-unstopped EXCLUDED from levels · intrabar fill PRIMARY (variant d), close-stop = sens
  equal-notional mean return beside every R read
  clustering = EPISODE x NAME (F2)        · leave-COVID-out + leave-one-episode-out on every
                                            promotion-bearing cell (F1)
A1b peer set = primary thematic basket's members; GICS sector fallback; both coverages reported
against a fire-weighted 60% floor on the union. Threshold grid {15,20,25,30}% reported IN FULL —
the shipped threshold is an operator aggressiveness choice, not a statistical claim.
"""
from __future__ import annotations

import json
import multiprocessing as mp
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

import study as S

HERE = Path(__file__).resolve().parent
OUT = HERE.parents[1].parent            # .../blocked_entry_study_r3

B, SEED = 2000, 20260810
CAP = 10.0
M = "m0.5"                              # FIXED (F6)
GRID = (0.15, 0.20, 0.25, 0.30)
COVID = (pd.Timestamp("2020-02-15"), pd.Timestamp("2020-06-30"))
GICS = ("Communication Services", "Consumer Discretionary", "Consumer Staples", "Energy",
        "Financials", "Health Care", "Industrials", "Information Technology", "Materials",
        "Real Estate", "Utilities")
EXEMPLARS = ("UEC", "HL", "NEM", "9988.HK", "600547.SS", "002716.SZ")
CITED = {"UEC": ["2026-08-03"], "HL": ["2026-06-16", "2026-06-25"]}
FLOOR = 0.60


# ------------------------------------------------------ repaired aggregate ---
def agg(df: pd.DataFrame) -> dict:
    """The §7 repaired level. Intrabar R, censored-unstopped dropped, capped at +10R."""
    live = df[~df["cens"]]
    r = live["R"].dropna()
    if r.empty:
        return {"n": 0, "n_censored_excluded": int(df["cens"].sum())}
    cap = r.clip(upper=CAP)
    lo, hi = (r.quantile(0.01), r.quantile(0.99)) if len(r) >= 20 else (r.min(), r.max())
    cens = df[df["cens"]]
    return {
        "n": int(len(r)), "n_names": int(live["sym"].nunique()),
        "mean_R_capped10": float(cap.mean()),
        "mean_R_winsor99": float(r.clip(lo, hi).mean()),
        "mean_R_raw": float(r.mean()), "median_R": float(r.median()),
        "equal_notional_mean_ret": float(live["ret"].mean()),
        "median_ret": float(live["ret"].median()),
        "win_rate": float((live["ret"] > 0).mean()),
        "n_censored_excluded": int(len(cens)),
        "censored_mark_mean_R": float(cens["R"].dropna().mean()) if len(cens) else None,
    }


def episodes_and_clusters(df: pd.DataFrame, cal: np.ndarray, gap: int = 21) -> pd.DataFrame:
    """Episode label from fire-date gaps; cluster = episode x name (F2)."""
    d = df.copy()
    if d.empty:
        d["episode"] = []; d["cluster"] = []
        return d
    u = np.unique(d["_kt"].to_numpy())
    pos = np.searchsorted(cal, u)
    lab = np.concatenate([[0], np.cumsum(np.diff(pos) > gap)]) if u.size > 1 else np.array([0])
    m = pd.Series(lab, index=u)
    d["episode"] = d["_kt"].map(m)
    d["cluster"] = d["episode"].astype(str) + "|" + d["sym"]
    return d


def boot(df: pd.DataFrame, by: str, stat="capped") -> dict:
    """Cluster bootstrap. by='cluster' (episode x name, the §7 unit), 'episode', or 'entry_date'."""
    live = df[~df["cens"]].dropna(subset=["R"])
    if live.empty:
        return {"point": None, "ci_lo": None, "ci_hi": None, "n_clusters": 0}
    v = live["R"].clip(upper=CAP).to_numpy() if stat == "capped" else live["ret"].to_numpy()
    keys = live[by].to_numpy()
    uniq, inv = np.unique(keys, return_inverse=True)
    sums = np.bincount(inv, weights=v, minlength=uniq.size)
    cnts = np.bincount(inv, minlength=uniq.size).astype(float)
    rng = np.random.default_rng(SEED)
    idx = rng.integers(0, uniq.size, size=(B, uniq.size))
    with np.errstate(invalid="ignore"):
        draws = sums[idx].sum(1) / cnts[idx].sum(1)
    d = draws[np.isfinite(draws)]
    return {"point": float(v.mean()), "ci_lo": float(np.percentile(d, 2.5)),
            "ci_hi": float(np.percentile(d, 97.5)), "n_clusters": int(uniq.size),
            "n_fires": int(v.size)}


def equal_date(df: pd.DataFrame) -> dict:
    live = df[~df["cens"]].dropna(subset=["R"])
    if live.empty:
        return {"point": None}
    g = live.assign(c=live["R"].clip(upper=CAP)).groupby("entry_date")["c"]
    per = g.mean()
    dates = per.index.to_numpy()
    rng = np.random.default_rng(SEED)
    idx = rng.integers(0, dates.size, size=(B, dates.size))
    draws = per.to_numpy()[idx].mean(1)
    return {"point": float(per.mean()), "ci_lo": float(np.percentile(draws, 2.5)),
            "ci_hi": float(np.percentile(draws, 97.5)), "n_dates": int(dates.size)}


def loco_loo(df: pd.DataFrame) -> dict:
    """Leave-COVID-out and leave-one-episode-out — a cell whose premium dies ex-COVID is dead."""
    live = df[~df["cens"]].dropna(subset=["R"])
    if live.empty:
        return {}
    ed = pd.DatetimeIndex(live["entry_date"])
    ex = live[~((ed >= COVID[0]) & (ed <= COVID[1]))]
    covid = live[(ed >= COVID[0]) & (ed <= COVID[1])]
    full = float(live["R"].clip(upper=CAP).mean())
    out = {"full": full, "n_full": int(len(live)),
           "ex_covid": float(ex["R"].clip(upper=CAP).mean()) if len(ex) else None,
           "n_ex_covid": int(len(ex)), "n_covid": int(len(covid)),
           "covid_share_of_fires": float(len(covid) / len(live)),
           "covid_share_of_R": (float(covid["R"].clip(upper=CAP).sum()
                                      / live["R"].clip(upper=CAP).sum())
                                if live["R"].clip(upper=CAP).sum() else None)}
    drops = {}
    for e in sorted(live["episode"].unique()):
        k = live[live["episode"] != e]
        if len(k):
            drops[int(e)] = float(k["R"].clip(upper=CAP).mean())
    if drops:
        out["loo_episode_min"] = min(drops.values())
        out["loo_episode_max"] = max(drops.values())
        out["loo_worst_episode"] = int(min(drops, key=lambda k: drops[k]))
        out["n_episodes"] = len(drops)
    return out


# ------------------------------------------------------------- peer sets -----
def build_peer_maps(panel: set[str]) -> tuple[dict, dict, dict]:
    """basket_map: ticker -> primary basket id; sector_map: ticker -> GICS; defs: basket -> members."""
    d = S.MACRO / "data"
    ts = pd.read_parquet(d / "breadth" / "ticker_sectors.parquet")
    sector = {t: s for t, s in zip(ts["ticker"], ts["sector"]) if s in GICS}
    themes: dict[str, list] = {}
    for f in sorted((d / "us_prophet_rank" / "candidates").glob("*.parquet")):
        c = pd.read_parquet(f)
        if "sector" in c.columns:
            for t, s in zip(c["ticker"], c["sector"]):
                if isinstance(s, str) and s in GICS:
                    sector.setdefault(t, s)
        col = next((x for x in ("theme_membership_ids", "theme_ids", "basket_ids", "themes")
                    if x in c.columns), None)
        if col:
            for t, v in zip(c["ticker"], c[col]):
                if t in themes:
                    continue
                ids = None
                if isinstance(v, (list, tuple, np.ndarray)) and len(v):
                    ids = [str(x) for x in v]
                elif isinstance(v, str) and v.strip() and v.strip() not in ("[]", "null"):
                    try:
                        p = json.loads(v)
                        ids = [str(x) for x in p] if isinstance(p, list) else [v.strip()]
                    except Exception:
                        ids = [x.strip() for x in v.split(",") if x.strip()]
                if ids:
                    themes[t] = ids
    members: dict[str, list[str]] = {}
    for t, ids in themes.items():
        for i in ids:
            members.setdefault(i, []).append(t)
    # primary basket = the SMALLEST basket the name belongs to (most thematically specific);
    # ties broken by id for determinism.
    basket = {}
    for t, ids in themes.items():
        cand = [i for i in ids if len(members.get(i, [])) >= 5]
        if cand:
            basket[t] = min(sorted(cand), key=lambda i: len(members[i]))
    return ({k: v for k, v in basket.items() if k in panel},
            {k: v for k, v in sector.items() if k in panel}, members)


def _dd_worker(sym: str):
    try:
        df = S.load_ohlc(sym)
    except Exception:
        return None
    if df is None:
        return None
    c = df["close"].astype("float64")
    return (sym, df.index.values.astype("datetime64[D]").astype("int32"),
            (c / c.rolling(252, min_periods=60).max() - 1).to_numpy("float32"))


def peer_median_panel(groups: dict[str, list[str]], dd: dict) -> dict[str, pd.Series]:
    out = {}
    for g, mem in groups.items():
        mem = [m for m in mem if m in dd]
        if len(mem) < 5:
            continue
        D = pd.DataFrame({m: pd.Series(dd[m][1], index=dd[m][0]) for m in mem}).sort_index()
        out[g] = D.median(axis=1)
    return out


# ------------------------------------------------------------- dead arm ------
def dead_events() -> tuple[list[dict], dict]:
    """Close-only signal replay + close-derived stop proxy on the delisted tape."""
    d = S.MACRO / "data"
    raw = pd.read_parquet(d / "edgar" / "dead_name_prices.parquet")
    cov = json.loads((d / "edgar" / "_dead_name_price_coverage.json").read_text())
    quar = json.loads((d / "quarantine" / "dead_name_prices_spliced.json").read_text())
    qnames = {f["ticker"] for f in quar.get("findings", [])}
    live_panel = ({p.stem for p in (d / "baskets" / "ohlcv").glob("*.parquet")}
                  | {p.stem for p in (d / "stocks").glob("*.parquet")})
    raw["date"] = pd.DatetimeIndex(raw["date"]).tz_localize(None)
    all_t = set(raw["ticker"].unique())
    collide = all_t & live_panel                      # BBBY-style ticker reuse -> ambiguous
    drop = collide | qnames
    use = sorted(all_t - drop)
    meta = {"n_dead_tickers": len(all_t), "n_quarantined": len(qnames),
            "quarantined": sorted(qnames), "n_ticker_reuse_collisions": len(collide),
            "collision_examples": sorted(collide)[:20], "n_used": len(use),
            "coverage_json": {k: cov.get(k) for k in
                              ("n_dead_universe", "n_with_prices", "price_coverage_frac",
                               "delisting_reason", "n_imputed_bankruptcies", "universe_basis")},
            "imputed_bankruptcy_rows": int((raw["source"] == "imputed_bankruptcy").sum())}
    bank = set(raw.loc[raw["source"] == "imputed_bankruptcy", "ticker"].unique())
    meta["imputed_bankruptcy_names"] = sorted(bank)

    evs: list[dict] = []
    for sym, g in raw[raw["ticker"].isin(use)].groupby("ticker"):
        c = g.set_index("date")["close"].sort_index().dropna()
        c = c[~c.index.duplicated(keep="last")]
        if len(c) < 340:
            continue
        try:
            sig = S.oracle.compute_signals(c)
        except Exception:
            continue
        if sig.empty:
            continue
        rows = sig.dropna(subset=["macd", "sig", "k", "d", "rsi14"])
        if len(rows) < 40:
            continue
        od, cd, _ = S.oracle._3d_groups(c, 0)
        didx = c.index
        bo = didx.searchsorted(od); bc = didx.searchsorted(cd)
        pos_of = {ts: j for j, ts in enumerate(od)}
        cv = c.to_numpy(float)
        # close-derived ATR proxy: Wilder RMA of |close-to-close|
        atr = S.oracle._rma(pd.Series(np.abs(np.diff(cv, prepend=cv[0]))), 14).to_numpy()
        raw_f = (rows["CB"] | rows["revBuy"]).to_numpy(bool)
        bb = rows["bear_block"].to_numpy(bool)
        known = pd.DatetimeIndex(rows["known_ts"])
        for i in np.flatnonzero(raw_f & bb):
            j = pos_of.get(rows.index[i])
            if j is None or j < 2:
                continue
            kp = int(didx.searchsorted(known[i]))
            ei = kp + 1
            if ei >= len(didx) - 5:
                continue
            base = float(np.min(cv[bo[j - 2]:bc[j] + 1]))
            a = float(atr[kp])
            if not np.isfinite(a) or a <= 0:
                continue
            entry = float(cv[ei])
            stop = base - 0.5 * a
            R = entry - stop
            if R <= 0 or R / entry < 0.005:
                continue
            end = min(len(cv), ei + 253)
            w = cv[ei:end]
            below = w < stop
            si = int(np.argmax(below)) if below.any() else -1
            terminal = end >= len(cv)          # ran to the name's LAST bar = delisting
            if si >= 0:
                px, why = float(w[si]), "stop"
            elif terminal:
                px, why = float(w[-1]), "delisted"
            else:
                px, why = float(w[-1]), "time252"
            floor_px = 0.0 if (why == "delisted" and sym in bank) else px
            evs.append({"sym": sym, "arm": "blocked", "market": "US_DEAD",
                        "entry_date": str(didx[ei].date()), "known_ts": str(known[i].date()),
                        "R": (px - entry) / R, "ret": px / entry - 1, "cens": False,
                        "R_floor": (floor_px - entry) / R, "ret_floor": floor_px / entry - 1,
                        "reason": why, "is_bankrupt": sym in bank})
    return evs, meta


def diff_boot(a: pd.DataFrame, b: pd.DataFrame) -> dict:
    """cell - complement, resampling the UNION of episode x name clusters jointly."""
    la, lb = a[~a["cens"]].dropna(subset=["R"]), b[~b["cens"]].dropna(subset=["R"])
    if la.empty or lb.empty:
        return {"point": None}
    keys = np.union1d(la["cluster"].unique(), lb["cluster"].unique())
    def acc(df):
        i = pd.Index(keys).get_indexer(df["cluster"])
        s = np.bincount(i, weights=df["R"].clip(upper=CAP), minlength=keys.size)
        n = np.bincount(i, minlength=keys.size).astype(float)
        return s, n
    sa, na = acc(la); sb, nb = acc(lb)
    rng = np.random.default_rng(SEED)
    idx = rng.integers(0, keys.size, size=(B, keys.size))
    with np.errstate(invalid="ignore"):
        d = sa[idx].sum(1) / na[idx].sum(1) - sb[idx].sum(1) / nb[idx].sum(1)
    d = d[np.isfinite(d)]
    return {"point": float(la["R"].clip(upper=CAP).mean() - lb["R"].clip(upper=CAP).mean()),
            "ci_lo": float(np.percentile(d, 2.5)), "ci_hi": float(np.percentile(d, 97.5)),
            "n_clusters": int(keys.size)}


def main() -> int:
    d = S.MACRO / "data"
    panel = ({p.stem for p in (d / "baskets" / "ohlcv").glob("*.parquet")}
             | {p.stem for p in (d / "stocks").glob("*.parquet")})
    basket, sector, members = build_peer_maps(panel)
    print(f"[peers] basket-mapped {len(basket)}/{len(panel)} = {len(basket)/len(panel):.1%}; "
          f"GICS {len(sector)/len(panel):.1%}; union "
          f"{len(set(basket)|set(sector))/len(panel):.1%}", flush=True)

    syms = sorted(panel | set(EXEMPLARS))
    with mp.Pool(20) as pool:
        chunks = pool.map(S._worker, [(s, S.ANCHOR) for s in syms], chunksize=8)
    rows = []
    for c in chunks:
        for e in c:
            if e["arm"] != "blocked":
                continue
            r = e[M]
            rows.append({"sym": e["sym"], "market": e["market"],
                         "entry_date": e["entry_date"], "known_ts": e["known_ts"],
                         "era": "design" if e["entry_date"] <= S.DESIGN_END else "verdict",
                         "R": r["d_R"], "ret": r["d_ret"],
                         "cens": r["d_reason"] == "censored",
                         "R_close": r["a_R"], "ret_close": r["a_ret"],
                         "cens_close": r["a_reason"] == "censored"})
    ev = pd.DataFrame(rows)
    ev["_kt"] = pd.DatetimeIndex(ev["known_ts"]).values.astype("datetime64[D]").astype("int32")
    print(f"[events] blocked n={len(ev)} US={int((ev.market=='US').sum())}", flush=True)

    dd: dict = {}
    day = Counter()
    with mp.Pool(20) as pool:
        for res in pool.imap_unordered(_dd_worker, sorted(panel), chunksize=16):
            if res is None:
                continue
            sym, days, v = res
            day.update(days.tolist())
            dd[sym] = (days, v)
    cal = np.array(sorted(day))
    bgroups = {b: [t for t in members.get(b, []) if t in dd] for b in set(basket.values())}
    sgroups: dict[str, list[str]] = {}
    for t, s in sector.items():
        if t in dd:
            sgroups.setdefault(s, []).append(t)

    # peer dd per event: primary basket (leave-one-out), else GICS sector (leave-one-out)
    peer = np.full(len(ev), np.nan)
    src = np.array(["none"] * len(ev), dtype=object)
    for gmap, groups, tag in ((basket, bgroups, "basket"), (sector, sgroups, "sector")):
        assign = ev["sym"].map(gmap)
        for g, mem in groups.items():
            if len(mem) < 5:
                continue
            D = pd.DataFrame({m2: pd.Series(dd[m2][1], index=dd[m2][0]) for m2 in mem}).sort_index()
            idx_, vals = D.index.to_numpy(), D.to_numpy("float32")
            cols = {c2: i for i, c2 in enumerate(D.columns)}
            sel = np.flatnonzero((assign == g).to_numpy() & ~np.isfinite(peer))
            if not sel.size:
                continue
            pos = np.searchsorted(idx_, ev["_kt"].to_numpy()[sel], side="right") - 1
            for ei, p in zip(sel, pos):
                if p < 0:
                    continue
                row = vals[p]; fin = np.isfinite(row)
                j = cols.get(ev["sym"].iat[ei])
                if j is not None and fin[j]:
                    fin = fin.copy(); fin[j] = False
                if fin.any():
                    peer[ei] = float(np.median(row[fin])); src[ei] = tag
    ev["peer_dd"] = peer; ev["peer_src"] = src

    us = ev[ev.market == "US"]
    cov = {
        "basket_names_pct": len(basket) / len(panel), "gics_names_pct": len(sector) / len(panel),
        "union_names_pct": len(set(basket) | set(sector)) / len(panel),
        "fire_weighted_union": float(us["peer_dd"].notna().mean()),
        "fire_weighted_basket": float((us["peer_src"] == "basket").mean()),
        "fire_weighted_sector": float((us["peer_src"] == "sector").mean()),
        "floor": FLOOR,
    }
    cov["passes_fire_weighted_floor"] = cov["fire_weighted_union"] >= FLOOR
    print(f"[coverage] fire-weighted union {cov['fire_weighted_union']:.1%} "
          f"(basket {cov['fire_weighted_basket']:.1%} + sector {cov['fire_weighted_sector']:.1%}) "
          f"-> {'PASS' if cov['passes_fire_weighted_floor'] else 'FAIL'}", flush=True)

    hd = us[(us.era == "verdict") & us.peer_dd.notna()].copy()
    hd = episodes_and_clusters(hd, cal)
    des = us[(us.era == "design") & us.peer_dd.notna()]

    grid: dict = {}
    for th in GRID:
        cell = hd[hd.peer_dd <= -th].copy()
        comp = hd[hd.peer_dd > -th].copy()
        cell = episodes_and_clusters(cell, cal); comp = episodes_and_clusters(comp, cal)
        dc = des[des.peer_dd <= -th]; dk = des[des.peer_dd > -th]
        sep = (abs(dc["R"].clip(upper=CAP).mean() - dk["R"].clip(upper=CAP).mean())
               if len(dc) and len(dk) else None)
        grid[f"{th:.2f}"] = {
            "design_abs_separation": None if sep is None else float(sep),
            "n_design_cell": int(len(dc)),
            "cell_level": agg(cell), "complement_level": agg(comp),
            "cell_boot_cluster": boot(cell, "cluster"),
            "cell_boot_episode": boot(cell, "episode"),
            "cell_equal_date": equal_date(cell),
            "diff_vs_complement": diff_boot(cell, comp),
            "loco_loo": loco_loo(cell),
            "admit_share_of_mapped_heldout": float((hd.peer_dd <= -th).mean()),
        }
    sel_th = max([k for k in grid if grid[k]["design_abs_separation"] is not None],
                 key=lambda k: grid[k]["design_abs_separation"], default="0.20")
    print(f"[design] A1b threshold selected {sel_th} (abs-sep "
          f"{grid[sel_th]['design_abs_separation']:.3f})", flush=True)

    # ---- dead arm ----------------------------------------------------------
    devs, dmeta = dead_events()
    dev = pd.DataFrame(devs)
    dead_summary = {"meta": dmeta, "n_dead_blocked_fires": int(len(dev))}
    if len(dev):
        dev["_kt"] = pd.DatetimeIndex(dev["known_ts"]).values.astype("datetime64[D]").astype("int32")
        dev["era"] = np.where(dev["entry_date"] <= S.DESIGN_END, "design", "verdict")
        dev["peer_dd"] = dev["sym"].map(sector)          # dead names: GICS peers only
        dhd = dev[dev.era == "verdict"].copy()
        dead_summary["n_heldout"] = int(len(dhd))
        dead_summary["reason_mix"] = dev["reason"].value_counts().to_dict()
        dead_summary["n_bankrupt_names"] = int(dev["is_bankrupt"].sum())
        base = hd.copy()
        for label, rcol, retcol in (("primary", "R", "ret"), ("floor", "R_floor", "ret_floor")):
            dd2 = dhd.assign(R=dhd[rcol], ret=dhd[retcol], cens=False)
            comb = pd.concat([base[["sym", "R", "ret", "cens", "entry_date"]],
                              dd2[["sym", "R", "ret", "cens", "entry_date"]]], ignore_index=True)
            dead_summary[f"pooled_level_with_dead_{label}"] = agg(comb)
            dead_summary[f"dead_only_level_{label}"] = agg(dd2)
        dead_summary["pooled_level_survivor"] = agg(base)
    res_out = {}

    # ---- exemplar admission per threshold ----------------------------------
    tape_k = int(cal.max()); tape_d = str(pd.Timestamp(tape_k, unit="D").date())
    exem: dict = {"tape_end": tape_d, "rows": []}
    for sym, dates in CITED.items():
        g = basket.get(sym); s2 = sector.get(sym)
        grp, mem = ("basket", bgroups.get(g, [])) if g else ("sector", sgroups.get(s2, []))
        for fd in dates:
            t = pd.Timestamp(fd); post = t > pd.Timestamp(tape_d)
            k = int(np.datetime64((pd.Timestamp(tape_d) if post else t).date(), "D").astype("int32"))
            pv = None
            if len(mem) >= 5:
                D = pd.DataFrame({m2: pd.Series(dd[m2][1], index=dd[m2][0])
                                  for m2 in mem if m2 in dd}).sort_index()
                p = int(np.searchsorted(D.index.to_numpy(), k, side="right")) - 1
                if p >= 0:
                    row = D.to_numpy("float32")[p]; row = row[np.isfinite(row)]
                    pv = float(np.median(row)) if row.size else None
            exem["rows"].append({"sym": sym, "fire_date": fd, "peer_src": grp,
                                 "peer_group": g or s2, "n_peers": len(mem),
                                 "postdates_tape": bool(post), "peer_dd": pv,
                                 "admitted": {f"{th:.0%}": (pv is not None and pv <= -th)
                                              for th in GRID}})
    for sym in ("9988.HK", "600547.SS", "002716.SZ"):
        exem["rows"].append({"sym": sym, "fire_date": None, "peer_src": None,
                             "note": "non-US: no basket/GICS peer set in this panel — A1b not computable"})

    # ---- current membership per threshold ----------------------------------
    now: dict = {"as_of": tape_d, "by_threshold": {}}
    gnow = {}
    for tag, groups in (("basket", bgroups), ("sector", sgroups)):
        for g, mem in groups.items():
            mem = [m2 for m2 in mem if m2 in dd]
            if len(mem) < 5:
                continue
            D = pd.DataFrame({m2: pd.Series(dd[m2][1], index=dd[m2][0]) for m2 in mem}).sort_index()
            p = int(np.searchsorted(D.index.to_numpy(), tape_k, side="right")) - 1
            if p < 0:
                continue
            row = D.to_numpy("float32")[p]; row = row[np.isfinite(row)]
            if row.size:
                gnow[f"{tag}:{g}"] = float(np.median(row))
    for th in GRID:
        q = sorted([g for g, v in gnow.items() if v <= -th])
        now["by_threshold"][f"{th:.0%}"] = {"n_qualifying": len(q), "groups": q[:25]}
    now["deepest_groups"] = dict(sorted(gnow.items(), key=lambda x: x[1])[:12])

    res_out = {"meta": {"prereg": "§7 AMENDMENT 2", "instrument_commit": "2ad6db7712b",
                        "signal_sha256": S.SIGNAL_SOURCE_SHA256, "m_fixed": M,
                        "aggregate": "mean R capped +10R, censored-unstopped excluded, "
                                     "intrabar fill primary", "B": B, "seed": SEED,
                        "cluster_unit": "episode x name", "cap": CAP,
                        "covid_window": [str(COVID[0].date()), str(COVID[1].date())]},
               "coverage": cov, "grid": grid, "design_selected_threshold": sel_th,
               "dead_arm": dead_summary, "exemplars": exem, "current_membership": now}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "r3_results.json").write_text(json.dumps(res_out, indent=1, default=str))
    ev.drop(columns=["_kt"]).to_parquet(OUT / "r3_events.parquet")
    if len(dev):
        dev.drop(columns=["_kt"]).to_parquet(OUT / "r3_dead_events.parquet")

    print(f"\n{'thr':>5}{'cellR':>8}{'clusCI':>17}{'epiCI':>17}{'eqdate':>8}"
          f"{'diff':>8}{'diffCI':>17}{'exCOVID':>9}{'LOOmin':>8}{'fires':>7}{'clus':>6}{'epis':>6}")
    print("-" * 118)
    for th, g in grid.items():
        L, cb, eb, ed2, df2, ll = (g["cell_level"], g["cell_boot_cluster"], g["cell_boot_episode"],
                                   g["cell_equal_date"], g["diff_vs_complement"], g["loco_loo"])
        print(f"{th:>5}{L['mean_R_capped10']:>8.3f}"
              f"[{cb['ci_lo']:>6.3f},{cb['ci_hi']:>6.3f}]"
              f"[{eb['ci_lo']:>6.3f},{eb['ci_hi']:>6.3f}]{ed2['point']:>8.3f}"
              f"{df2['point']:>8.3f}[{df2['ci_lo']:>6.3f},{df2['ci_hi']:>6.3f}]"
              f"{ll.get('ex_covid', float('nan')):>9.3f}{ll.get('loo_episode_min', float('nan')):>8.3f}"
              f"{L['n']:>7}{cb['n_clusters']:>6}{ll.get('n_episodes', 0):>6}")
    print(f"\n[dead] {json.dumps({k: v for k, v in dead_summary.items() if not isinstance(v, dict)})}")
    print(f"-> {OUT/'r3_results.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
