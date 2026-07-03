#!/usr/bin/env python3
"""R1 phase-0 — connect-removal (调出) risk gate, cause-controlled.

Pre-registered in research/R1_REMOVAL_GATE_PREREG.md (committed before this run).

The H-INCL2 exploratory found removed HK Connect names underperform HSI (~-4.7% CAR
+20d, HAC t~-2.8) but flagged reverse causality: the semi-annual review removes names
BECAUSE they have already deteriorated. R1 isolates the INCREMENTAL removal effect via a
matched-decile design + trailing-3M control:

  CAR_h ~ b0 + b1*removal_dummy + b2*trail3m   over a stacked matched panel
          (each removed name matched to 2 non-removed union names in its trail3m decile
           at the same announce date; nearest-neighbour, deterministic, no RNG)

b1 = the removal effect beyond the deterioration that caused it. Inference is
EPISODE-CLUSTERED (episode = unique announce date; K is the effective-N ceiling).

GATED family = {H_REM@+5d, H_REM@+20d}. GO-for-demote (H4-strength incremental):
  HAC t<=-2.0 (+20d) AND split-half sign-stable AND BH-FDR reject AND survivorship-robust.

Fills = next-valid-CLOSE (hk open unpopulated in deep stores). Suspension rule: need a
valid print within 5 sessions after fill else EXCLUDE. Reads the gitignored ext store from
the absolute sibling worktree path. NO WIRING.
"""
from __future__ import annotations
import glob
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.validation import (  # noqa: E402
    bootstrap_effective_t, deflated_sharpe, dsr_verdict, newey_west_tstat,
    benjamini_hochberg, ret_moments,
)
from engine.trial_ledger import TrialLedger  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT_LOCAL = os.path.join(HERE, "data", "hk_stocks_ext")
EXT_SIBLING = os.path.join(
    HERE, "..", "amazing-blackburn-5d2027", "data", "hk_stocks_ext")
HK_DIR = os.path.join(HERE, "data", "hk_stocks")
DEEP_FILE = os.path.join(HERE, "data", "hk_search", "closes_deep.parquet")
HSI_FILE = os.path.join(HERE, "data", "hk", "_HSI.parquet")
ROSTER = os.path.join(HERE, "data", "hk_connect_roster", "roster.parquet")

TRAIL = 63            # trailing-3M deterioration window (trading days)
STALE_SESS = 5        # suspension / staleness window
HORIZONS = [5, 20]    # gated forward CAR horizons
PRE_WIN = 20          # descriptive pre-announcement window (-20..0)
N_CONTROLS = 2        # controls per removed name
N_TRIALS = 36         # PROGRAM-level multiplicity (masterplan section 6 ~36), declared floor
FAMILY = "r1_removal_gate_phase0"
_LED = TrialLedger.with_declared_budget(N_TRIALS, FAMILY)
MIN_EPISODES_POWER = 12   # below this -> NO-GO (underpowered)
# survivorship bound: phantom missing micro-cap removed names
PHANTOM_CAR = -0.30
DELIST_MONTHLY = 0.005    # base monthly delist rate; injected at 2x


def _ext_dir() -> str:
    if len(glob.glob(os.path.join(EXT_LOCAL, "*.parquet"))) >= 100:
        return EXT_LOCAL
    return os.path.normpath(EXT_SIBLING)


def load_close_union():
    """Union close matrix (ext ∪ hk_stocks ∪ closes_deep), dedup preferring longest history."""
    extd = _ext_dir()
    stamp = {"ext_dir": extd}
    cols: dict[str, pd.Series] = {}

    def _add(tkr, s):
        s = s[~s.index.duplicated(keep="last")].dropna()
        if s.empty:
            return
        cur = cols.get(tkr)
        if cur is None or s.count() > cur.count():
            cols[tkr] = s

    cd = pd.read_parquet(DEEP_FILE).sort_index()
    cd = cd[~cd.index.duplicated(keep="last")]
    for c in cd.columns:
        _add(c, cd[c])
    stamp["closes_deep"] = {"n_cols": cd.shape[1],
                            "range": [str(cd.index.min().date()), str(cd.index.max().date())]}

    hk_files = glob.glob(os.path.join(HK_DIR, "*.HK.parquet"))
    for f in hk_files:
        t = os.path.basename(f)[:-8]
        _add(t, pd.read_parquet(f, columns=["close"])["close"])
    stamp["hk_stocks"] = {"n_files": len(hk_files)}

    ext_files = glob.glob(os.path.join(extd, "*.parquet"))
    ext_min = None
    for f in ext_files:
        t = os.path.basename(f)[:-8]
        s = pd.read_parquet(f, columns=["close"])["close"]
        sm = s.dropna().index.min()
        ext_min = sm if ext_min is None else min(ext_min, sm)
        _add(t, s)
    stamp["hk_stocks_ext"] = {"n_files": len(ext_files),
                              "earliest_start": str(ext_min.date()) if ext_min is not None else None}

    close = pd.DataFrame(cols).sort_index()
    stamp["union_names"] = close.shape[1]
    stamp["union_range"] = [str(close.index.min().date()), str(close.index.max().date())]
    return close, stamp


def load_hsi():
    h = pd.read_parquet(HSI_FILE)["close"].sort_index()
    h = h[~h.index.duplicated(keep="last")].dropna()
    return h


def _pos_on_or_before(idx: pd.DatetimeIndex, d: pd.Timestamp):
    """integer position of the last index date <= d, or None."""
    p = idx.searchsorted(d, side="right") - 1
    return int(p) if p >= 0 else None


def trail3m(close: pd.Series, idx: pd.DatetimeIndex, d: pd.Timestamp):
    """raw simple return over the 63 valid trailing bars ending at last close <= d."""
    p = _pos_on_or_before(idx, d)
    if p is None or p < TRAIL:
        return None
    win = close.iloc[p - TRAIL:p + 1].dropna()
    if win.count() < TRAIL:
        return None
    c0, c1 = win.iloc[0], win.iloc[-1]
    if c0 is None or c0 <= 0 or pd.isna(c0) or pd.isna(c1):
        return None
    return float(c1 / c0 - 1.0)


def fill_pos(idx: pd.DatetimeIndex, d: pd.Timestamp):
    """first index position STRICTLY after announce date d (next-valid-close fill bar)."""
    p = idx.searchsorted(d, side="right")
    return int(p) if p < len(idx) else None


def fwd_car(close: pd.Series, idx: pd.DatetimeIndex, hsi: pd.Series,
            fill_p: int, h: int):
    """index-relative CAR (log) close-to-close over [fill, fill+h].

    Suspension: need a valid print within STALE_SESS sessions after the fill bar.
    Returns None on halt-at-fill, insufficient bars, or window past panel end.
    """
    if fill_p is None or fill_p + h >= len(idx):
        return None
    c_fill = close.iloc[fill_p]
    if pd.isna(c_fill) or c_fill <= 0:
        # halt at fill -> slide to next valid within STALE_SESS
        seg = close.iloc[fill_p:fill_p + STALE_SESS + 1]
        lv = seg.first_valid_index()
        if lv is None:
            return None
        fill_p = idx.get_indexer([lv])[0]
        if fill_p + h >= len(idx):
            return None
        c_fill = close.iloc[fill_p]
        if pd.isna(c_fill) or c_fill <= 0:
            return None
    # suspension check post-fill
    post = close.iloc[fill_p:fill_p + STALE_SESS + 1]
    if post.count() == 0:
        return None
    t_fill = idx[fill_p]
    t_exit = idx[fill_p + h]
    c_exit = close.iloc[fill_p + h]
    if pd.isna(c_exit):
        lv = close.iloc[fill_p:fill_p + h + 1].last_valid_index()
        if lv is None:
            return None
        c_exit = close.loc[lv]
        t_exit = lv
    # require enough common bars in-window
    stk_win = close.iloc[fill_p:fill_p + h + 1].dropna()
    if stk_win.count() < max(3, h // 2):
        return None
    r_stk = np.log(c_exit / c_fill)
    h1 = hsi.asof(t_fill)
    h2 = hsi.asof(t_exit)
    if pd.isna(h1) or pd.isna(h2) or h1 <= 0 or h2 <= 0:
        return None
    r_hsi = np.log(h2 / h1)
    return float(r_stk - r_hsi)


def pre_car(close: pd.Series, idx: pd.DatetimeIndex, hsi: pd.Series, d: pd.Timestamp):
    """descriptive -PRE_WIN..0 CAR ending at the last close <= d (index-relative log)."""
    p = _pos_on_or_before(idx, d)
    if p is None or p < PRE_WIN:
        return None
    c0 = close.iloc[p - PRE_WIN]
    c1 = close.iloc[p]
    if pd.isna(c0) or pd.isna(c1) or c0 <= 0:
        return None
    t0, t1 = idx[p - PRE_WIN], idx[p]
    h0, h1 = hsi.asof(t0), hsi.asof(t1)
    if pd.isna(h0) or pd.isna(h1) or h0 <= 0:
        return None
    return float(np.log(c1 / c0) - np.log(h1 / h0))


def ols_b1(y, x_dummy, x_trail):
    """OLS of y on [1, removal_dummy, trail3m]; return coefficient on removal_dummy."""
    X = np.column_stack([np.ones(len(y)), x_dummy, x_trail])
    try:
        beta, *_ = np.linalg.lstsq(X, np.asarray(y, float), rcond=None)
    except Exception:
        return None
    return float(beta[1])


def build_matched(close_df, hsi, roster):
    """Per horizon, build episode-level b1 series + collect descriptive pre-window CAR.

    Returns dict: horizon -> {episode_b1: {date: b1}, n_removed, n_events, ...}, plus
    pre_run stats and coverage stamp.
    """
    idx = close_df.index
    rem = roster[roster.action == "remove"].copy()
    rem_tickers_all = set(rem.ticker)
    union_names = list(close_df.columns)

    # coverage
    in_union = rem[rem.ticker.isin(set(union_names))]
    cov = {"remove_total": int(len(rem)),
           "remove_in_union": int(len(in_union)),
           "remove_not_in_union": int(len(rem) - len(in_union))}

    # precompute per-name close series
    series = {t: close_df[t] for t in union_names}

    # per horizon accumulate matched rows keyed by episode date
    per_h = {h: {} for h in HORIZONS}   # h -> {date: [(y, dummy, trail)]}
    pre_run_removed = []
    studiable_events = 0
    studiable_tickers = set()

    for d, grp in in_union.groupby("announce_date"):
        d = pd.Timestamp(d)
        removed_here = set(grp.ticker)
        fp = fill_pos(idx, d)
        if fp is None:
            continue

        # eligible control pool at d: union names, not removed at d, trail3m computable,
        # and (checked later per-horizon) forward CAR computable
        pool = {}
        for t in union_names:
            if t in removed_here:
                continue
            tm = trail3m(series[t], idx, d)
            if tm is None:
                continue
            pool[t] = tm
        if len(pool) < 20:
            continue
        pool_items = sorted(pool.items(), key=lambda kv: kv[1])
        pool_names = [t for t, _ in pool_items]
        pool_tr = np.array([v for _, v in pool_items])

        # decile edges on the control pool
        try:
            edges = np.quantile(pool_tr, np.linspace(0, 1, 11))
        except Exception:
            continue

        for t in removed_here:
            if t not in series:
                continue
            tr_r = trail3m(series[t], idx, d)
            if tr_r is None:
                continue
            fp_r = fill_pos(idx, d)
            # which decile does the removed name fall in
            dec = int(np.clip(np.searchsorted(edges, tr_r, side="right") - 1, 0, 9))
            lo, hi = edges[dec], edges[dec + 1]
            in_dec = [nm for nm, v in zip(pool_names, pool_tr) if lo <= v <= hi]
            # nearest-neighbour controls within decile (fallback: whole-pool NN)
            def nn(cands, k):
                cands = sorted(cands, key=lambda nm: abs(pool[nm] - tr_r))
                return cands[:k]
            ctrls = nn(in_dec, N_CONTROLS)
            fallback = len(ctrls) < N_CONTROLS
            if fallback:
                ctrls = nn(pool_names, N_CONTROLS)

            # compute forward CARs; removed name must be studiable at BASE horizon (+20)
            base_ok = fwd_car(series[t], idx, hsi, fp_r, max(HORIZONS)) is not None
            if not base_ok:
                continue
            studiable_events += 1
            studiable_tickers.add(t)
            # pre-window descriptive
            pc = pre_car(series[t], idx, hsi, d)
            if pc is not None:
                pre_run_removed.append(pc)

            for h in HORIZONS:
                y_r = fwd_car(series[t], idx, hsi, fp_r, h)
                if y_r is None:
                    continue
                rows = per_h[h].setdefault(d, [])
                rows.append((y_r, 1.0, tr_r))
                for c in ctrls:
                    y_c = fwd_car(series[c], idx, hsi, fill_pos(idx, d), h)
                    if y_c is None:
                        continue
                    rows.append((y_c, 0.0, pool[c]))

    # episode-level b1 per horizon (require >=1 removed + >=1 control + variation in dummy)
    result = {}
    for h in HORIZONS:
        ep_b1 = {}
        for d, rows in per_h[h].items():
            if len(rows) < 4:
                continue
            y = [r[0] for r in rows]
            dm = [r[1] for r in rows]
            tr = [r[2] for r in rows]
            if sum(dm) == 0 or sum(dm) == len(dm):
                continue  # no dummy variation
            b1 = ols_b1(y, dm, tr)
            if b1 is None or not np.isfinite(b1):
                continue
            ep_b1[str(pd.Timestamp(d).date())] = b1
        result[h] = ep_b1

    cov.update({"studiable_events": studiable_events,
                "studiable_tickers": len(studiable_tickers)})
    return {"per_horizon_b1": result, "pre_run_removed": pre_run_removed,
            "coverage": cov, "per_h_rows": per_h}


def episode_stats(ep_b1: dict, label: str):
    """HAC/split-half/DSR/bootstrap on the episode-level b1 series."""
    dates = sorted(ep_b1.keys())
    vals = [ep_b1[d] for d in dates]
    k = len(vals)
    out = {"label": label, "k_episodes": k}
    if k < MIN_EPISODES_POWER:
        out["verdict"] = "UNDERPOWERED"
        if k >= 2:
            s = pd.Series(vals)
            out["mean_b1"] = round(float(s.mean()), 5)
        return out
    s = pd.Series(vals, index=pd.DatetimeIndex(dates))
    nw = newey_west_tstat(s, lags=4)
    out["mean_b1"] = round(float(s.mean()), 5)
    out["hac_t"] = nw["t"]
    # one-sided (negative) p
    out["hac_p_1sided_neg"] = nw["p"] / 2.0 if s.mean() < 0 else 1.0 - nw["p"] / 2.0
    # split-half sign stability
    hh = k // 2
    s1, s2 = float(s.iloc[:hh].mean()), float(s.iloc[hh:].mean())
    out["splithalf"] = {"h1": round(s1, 5), "h2": round(s2, 5),
                        "sign_stable": bool(np.sign(s1) == np.sign(s2) and s1 != 0 and s2 != 0)}
    # bootstrap effective-t + 90% CI
    teff = bootstrap_effective_t(s, block=4, B=5000)
    out["t_eff"] = teff.get("t_eff") if teff else None
    # DSR (b1 series treated as monthly-scale for the haircut)
    mom = ret_moments(s)
    if mom is not None:
        sr, sk, ku, _ = mom
        dsr = deflated_sharpe(sr, sk, ku, T=k, ledger=_LED, family=FAMILY,
                              trading_year=12, t_eff=out["t_eff"])
        out["sharpe_monthlyscale"] = round(sr, 4)
        out["dsr"] = dsr["dsr"] if dsr else None
        out["dsr_verdict"] = dsr_verdict(dsr["dsr"]) if dsr else None
    # 90% CI
    boot = []
    rng = np.random.default_rng(7)
    arr = s.values
    for _ in range(5000):
        # block bootstrap, block=4
        bl = 4
        n_blocks = int(np.ceil(len(arr) / bl))
        starts = rng.integers(0, max(1, len(arr) - bl + 1), n_blocks)
        samp = np.concatenate([arr[st:st + bl] for st in starts])[:len(arr)]
        boot.append(samp.mean())
    out["ci90"] = [round(float(np.percentile(boot, 5)), 5),
                   round(float(np.percentile(boot, 95)), 5)]
    return out


def survivorship_bound(per_h_rows, primary_h=20):
    """Re-estimate episode b1 at +20d after injecting phantom removed rows at CAR=-30%.

    Phantoms are matched against the SAME control draw per episode (2x monthly delist rate
    applied to that episode's removed count). Checks whether the CONTROLLED b1 sign holds.
    """
    rows_by_ep = per_h_rows[primary_h]
    ep_b1 = {}
    for d, rows in rows_by_ep.items():
        if len(rows) < 4:
            continue
        dm = [r[1] for r in rows]
        n_removed = int(sum(dm))
        if n_removed == 0 or n_removed == len(rows):
            continue
        aug = list(rows)
        # phantom removed names at CAR=-30%, trail3m = median removed trail (proxy)
        rem_tr = [r[2] for r in rows if r[1] == 1.0]
        med_tr = float(np.median(rem_tr)) if rem_tr else 0.0
        kp = int(round(n_removed * DELIST_MONTHLY * 2)) or 1  # >=1 phantom per episode
        for _ in range(kp):
            aug.append((PHANTOM_CAR, 1.0, med_tr))
        y = [r[0] for r in aug]
        d_ = [r[1] for r in aug]
        tr = [r[2] for r in aug]
        b1 = ols_b1(y, d_, tr)
        if b1 is not None and np.isfinite(b1):
            ep_b1[str(pd.Timestamp(d).date())] = b1
    dates = sorted(ep_b1)
    vals = [ep_b1[d] for d in dates]
    if len(vals) < MIN_EPISODES_POWER:
        return {"k": len(vals), "mean_b1": round(float(np.mean(vals)), 5) if vals else None,
                "note": "underpowered"}
    s = pd.Series(vals, index=pd.DatetimeIndex(dates))
    nw = newey_west_tstat(s, lags=4)
    return {"k": len(vals), "mean_b1": round(float(s.mean()), 5), "hac_t": nw["t"],
            "sign_flip_vs_raw": None}  # sign compared in main()


def main():
    close_df, stamp = load_close_union()
    hsi = load_hsi()
    stamp["hsi_range"] = [str(hsi.index.min().date()), str(hsi.index.max().date())]
    roster = pd.read_parquet(ROSTER)

    built = build_matched(close_df, hsi, roster)
    per_b1 = built["per_horizon_b1"]

    trials = {}
    for h in HORIZONS:
        trials[f"H_REM@+{h}d"] = episode_stats(per_b1[h], f"H_REM@+{h}d")

    # BH-FDR across the 2 gated one-sided p-values (only for estimable cells)
    pv = {k: v["hac_p_1sided_neg"] for k, v in trials.items()
          if v.get("hac_p_1sided_neg") is not None}
    bh = benjamini_hochberg(pv, alpha=0.10) if pv else {}

    # descriptive pre-window
    pre = built["pre_run_removed"]
    pre_stats = {"n": len(pre),
                 "mean_pre_car": round(float(np.mean(pre)), 5) if pre else None,
                 "median_pre_car": round(float(np.median(pre)), 5) if pre else None}

    # survivorship bound at +20d
    sb = survivorship_bound(built["per_h_rows"], primary_h=20)
    raw20 = trials["H_REM@+20d"].get("mean_b1")
    if sb.get("mean_b1") is not None and raw20 is not None:
        sb["sign_flip_vs_raw"] = bool(np.sign(sb["mean_b1"]) != np.sign(raw20))

    # GO-for-demote gate (primary horizon +20d)
    p20 = trials["H_REM@+20d"]
    gate = {
        "hac_t_le_-2.0": bool(p20.get("hac_t") is not None and p20["hac_t"] <= -2.0),
        "splithalf_sign_stable": bool(p20.get("splithalf", {}).get("sign_stable")
                                      and p20.get("mean_b1", 0) < 0),
        "bh_fdr_reject_+20d": bool(bh.get("H_REM@+20d", {}).get("reject", False))
                              if isinstance(bh.get("H_REM@+20d"), dict) else False,
        "survivorship_no_sign_flip": bool(not sb.get("sign_flip_vs_raw", True)),
        "powered": bool(p20.get("k_episodes", 0) >= MIN_EPISODES_POWER),
    }
    if not gate["powered"]:
        verdict = "NO-GO (underpowered)"
    elif all(gate[k] for k in ("hac_t_le_-2.0", "splithalf_sign_stable",
                               "bh_fdr_reject_+20d", "survivorship_no_sign_flip")):
        verdict = "GO-for-demote"
    else:
        verdict = "NO-GO (effect not incremental)"

    out = {
        "stamp": stamp,
        "coverage": built["coverage"],
        "trials": trials,
        "bh_fdr": bh,
        "pre_window_descriptive": pre_stats,
        "survivorship_bound_+20d": sb,
        "gate": gate,
        "verdict": verdict,
        "params": {"trail": TRAIL, "horizons": HORIZONS, "n_controls": N_CONTROLS,
                   "stale_sess": STALE_SESS, "n_trials_declared": N_TRIALS,
                   "min_episodes_power": MIN_EPISODES_POWER,
                   "phantom_car": PHANTOM_CAR, "delist_monthly_2x": DELIST_MONTHLY},
    }
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
