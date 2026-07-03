#!/usr/bin/env python3
"""X1 — A-twin read-through phase-0 (HK & Canada masterplan §3, new mechanism).

Pre-registered in research/HK_CANADA_X1_PREREG.md (committed BEFORE this run).
Report only; NO wiring.

Thesis: the A-share twin of a dual-listed A/H name carries validated in-house state
(within-history 3M reversal / 1M momentum). Because A/H investor bases are segmented,
does the A-twin's price state predict the H leg's forward excess over HSI, INCREMENTAL
to the H leg's own (H4-killed) price state?

Data is gitignored/R2 → read from the session worktree absolute path. Run:
  python research/hk_x1_atwin_readthrough.py
"""
import json
import sys
import numpy as np
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.validation import (  # noqa: E402
    rank_ic, ic_summary, newey_west_tstat, bootstrap_effective_t,
    deflated_sharpe, benjamini_hochberg, ret_moments, cross_sectional_resid,
)
from engine.trial_ledger import TrialLedger  # noqa: E402

# --- data root: gitignored/R2, read from the session worktree absolute path ---------- #
DATA = Path("/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/"
            "amazing-blackburn-5d2027/data")
PAIRS = DATA / "hk_ah_panel/pairs.json"
PREMIUM = DATA / "hk_ah_panel/premium.parquet"
ADIR = DATA / "china_stocks"
HDIR = DATA / "hk_stocks"
HSI_F = DATA / "hk/_HSI.parquet"

OWN_WIN = 504          # ~2y trailing own-history window for the z-score
OWN_MIN = 252          # >=1y non-NaN required to z-score a pair on date t
R3M = 63               # ~3-month trailing return (trading days)
R1M = 21               # ~1-month trailing return
HALT_SESS = 5          # next-valid-print window (sessions) for entry
TOPN = 5               # equal-weight long top-5 H legs
MIN_PAIRS = 8          # min valid names per rebalance (H3 floor)
PROGRAM_BUDGET = 36    # program-level DSR haircut floor (masterplan §9; prereg §1)
FAMILY = "hkca_x1"
_LED = TrialLedger.with_declared_budget(PROGRAM_BUDGET, FAMILY)


def load():
    pairs = json.load(open(PAIRS))
    hsi = pd.read_parquet(HSI_F)["close"]
    hsi.index = pd.to_datetime(hsi.index)
    A, H = {}, {}
    for p in pairs:
        af, hf = ADIR / f"{p['a']}.parquet", HDIR / f"{p['h']}.parquet"
        a = pd.read_parquet(af)["close"]; a.index = pd.to_datetime(a.index)
        h = pd.read_parquet(hf)["close"]; h.index = pd.to_datetime(h.index)
        A[p["h"]] = a.sort_index()       # A series KEYED BY H-ticker (the pair id)
        H[p["h"]] = h.sort_index()
    prem = pd.read_parquet(PREMIUM); prem.index = pd.to_datetime(prem.index)
    return pairs, A, H, hsi, prem


# ---- signal builders (formed on the A leg, keyed by H-ticker) ----------------------- #
def own_z(series: pd.Series, lookret: int) -> pd.Series:
    """Within-history z-score of the trailing `lookret`-day return, over an OWN_WIN
    trailing window (min OWN_MIN). Invariant to a constant multiplicative TR drift over
    the lookback (prereg §2 caveat handled)."""
    r = series / series.shift(lookret) - 1.0
    out = pd.Series(index=r.index, dtype=float)
    vals = r.values
    for i in range(len(r)):
        if np.isnan(vals[i]):
            continue
        lo = max(0, i - OWN_WIN + 1)
        w = vals[lo:i + 1]
        w = w[~np.isnan(w)]
        if len(w) < OWN_MIN:
            continue
        sd = w.std(ddof=1)
        if sd <= 0:
            continue
        out.iloc[i] = (vals[i] - w.mean()) / sd
    return out


def own_pctile(series: pd.Series) -> pd.Series:
    """Trailing own-history percentile of a level series (reused for the premium in
    the interaction trial c). window OWN_WIN, min OWN_MIN."""
    out = pd.Series(index=series.index, dtype=float)
    vals = series.values
    for i in range(len(series)):
        if np.isnan(vals[i]):
            continue
        lo = max(0, i - OWN_WIN + 1)
        w = vals[lo:i + 1]
        w = w[~np.isnan(w)]
        if len(w) < OWN_MIN:
            continue
        out.iloc[i] = (w < vals[i]).sum() / len(w)
    return out


def trailing_ret(series: pd.Series, lookret: int) -> pd.Series:
    return series / series.shift(lookret) - 1.0


# ---- suspension-honest forward return (H3 fwd_excess, verbatim mechanism) ------------ #
def fwd_excess(hs: pd.Series, hsi: pd.Series, t, h: int):
    """H-leg excess vs HSI from the next real H close after t, over h bars.
    HK-halt rule: entry within HALT_SESS sessions after t; horizon-end close real;
    no forward-fill across gaps. Returns NaN if unfillable."""
    hs = hs.dropna()
    if hs.empty:
        return np.nan
    ep = hs.index.searchsorted(t, side="right")
    if ep >= len(hs):
        return np.nan
    entry_date = hs.index[ep]
    if (entry_date - t).days > HALT_SESS * 3 + 3:   # ~5 sessions guard (calendar days)
        return np.nan
    if ep + h >= len(hs):
        return np.nan
    hr = hs.iloc[ep + h] / hs.iloc[ep] - 1.0
    exit_date = hs.index[ep + h]
    hb = hsi[(hsi.index >= entry_date) & (hsi.index <= exit_date)].dropna()
    if len(hb) < 2:
        return np.nan
    br = hb.iloc[-1] / hb.iloc[0] - 1.0
    return hr - br


def build_rebalances(A_sig: dict, H: dict, hsi, h: int,
                     H_ctrl: dict = None, prem_pctile: pd.DataFrame = None,
                     min_pairs: int = MIN_PAIRS):
    """Monthly rebalances. Each record = (signal, fwd_excess, H_own_ctrl, prem_pctile).
    A_sig: {htk: signal series}. H_ctrl: {htk: H-own trailing-return series} for the C1
    control. prem_pctile: DataFrame(date x htk) of premium own-pctile for trial c."""
    tks = list(A_sig.keys())
    # month-end grid from the union of signal dates
    allidx = pd.DatetimeIndex(sorted(set().union(*[A_sig[k].dropna().index for k in tks])))
    monthly = allidx.to_series().resample("ME").last().dropna()
    rows = []
    for t in monthly.values:
        t = pd.Timestamp(t)
        recs = {}
        for tk in tks:
            s = A_sig[tk].dropna()
            pos = s.index.searchsorted(t, side="right") - 1
            if pos < 0:
                continue
            sd = s.index[pos]
            if (t - sd).days > 10:        # signal must be fresh at month-end
                continue
            sv = s.iloc[pos]
            if np.isnan(sv):
                continue
            fx = fwd_excess(H[tk], hsi, t, h)
            if np.isnan(fx):
                continue
            ctrl = np.nan
            if H_ctrl is not None:
                c = H_ctrl[tk].dropna()
                cp = c.index.searchsorted(t, side="right") - 1
                ctrl = c.iloc[cp] if cp >= 0 else np.nan
            pp = np.nan
            if prem_pctile is not None and tk in prem_pctile.columns:
                pser = prem_pctile[tk].dropna()
                pp2 = pser.index.searchsorted(t, side="right") - 1
                pp = pser.iloc[pp2] if pp2 >= 0 else np.nan
            recs[tk] = (sv, fx, ctrl, pp)
        if len(recs) >= min_pairs:
            rows.append((t, recs))
    return rows


def eval_signal(rows):
    """rank-IC, C1-residual IC (vs H own return), top-5 excess, dividend-neutral L/S."""
    ics, ics_resid, top5, ls, dates = [], [], [], [], []
    for t, recs in rows:
        tks = list(recs.keys())
        sig = pd.Series({k: recs[k][0] for k in tks})
        fwd = pd.Series({k: recs[k][1] for k in tks})
        hctrl = pd.Series({k: recs[k][2] for k in tks})
        dates.append(t)
        ics.append(rank_ic(sig, fwd))
        # C1: residualize the A-signal against the H leg's OWN trailing return
        try:
            if hctrl.notna().sum() >= 10:
                sr = cross_sectional_resid(sig, pd.DataFrame({"h_own": hctrl}))
                ics_resid.append(rank_ic(sr, fwd) if len(sr) else np.nan)
            else:
                ics_resid.append(np.nan)
        except Exception:
            ics_resid.append(np.nan)
        order = sig.sort_values(ascending=False)
        top = order.index[:TOPN]
        top5.append(float(np.mean([fwd[k] for k in top])))     # equal-weight top-5
        n = len(order)
        k = max(1, n // 3)                                      # tercile L/S
        thi, tlo = order.index[:k], order.index[-k:]
        ls.append(float(np.mean([fwd[x] for x in thi]) - np.mean([fwd[x] for x in tlo])))
    return (pd.Series(ics, index=dates), pd.Series(ics_resid, index=dates),
            pd.Series(top5, index=dates), pd.Series(ls, index=dates))


def stats_block(ic, icr, top5, ls, h, label):
    nw_ic = ic_summary(ic.dropna(), periods_per_year=12)
    lag = 2 if h >= 63 else (1 if h >= 21 else 0)
    nw_ex = newey_west_tstat(top5.dropna(), lags=lag)
    nw_ls = newey_west_tstat(ls.dropna(), lags=lag)
    nw_icr = ic_summary(icr.dropna(), periods_per_year=12)
    ser = top5.dropna()
    rm = ret_moments(ser)
    sr_m, skew, kurt = (rm[0], rm[1], rm[2]) if rm else (np.nan, None, None)
    teff = bootstrap_effective_t(ser, block=3)
    t_eff = teff.get("t_eff") if teff else None
    dsr = (deflated_sharpe(sr_m, skew, kurt, len(ser), ledger=_LED, family=FAMILY,
                           trading_year=12, t_eff=t_eff if (t_eff and t_eff >= 3) else None)
           if rm else None)
    raw_ic = nw_ic.get("mean_ic")
    res_ic = nw_icr.get("mean_ic")
    c1_keep = (round(res_ic / raw_ic, 3) if (raw_ic not in (None, 0) and res_ic is not None)
               else None)
    return {
        "label": label, "h": h, "n_rebal": len(ser),
        "mean_ic": raw_ic, "ic_ir": nw_ic.get("ic_ir"), "ic_t_hac": nw_ic.get("t_hac"),
        "ic_p_hac": nw_ic.get("p_hac"), "ic_hit": nw_ic.get("hit"),
        "c1_resid_ic": res_ic, "c1_resid_ic_t": nw_icr.get("t_hac"),
        "c1_keep_frac": c1_keep, "c1_sign_ok": (bool(res_ic is not None and raw_ic is not None
                                                and np.sign(res_ic) == np.sign(raw_ic))),
        "top5_mean": nw_ex.get("mean"), "top5_t_hac": nw_ex.get("t"), "top5_p": nw_ex.get("p"),
        "ls_mean": nw_ls.get("mean"), "ls_t_hac": nw_ls.get("t"), "ls_p": nw_ls.get("p"),
        "sr_monthly": round(float(sr_m), 4) if rm else None, "t_eff": t_eff, "t_raw": len(ser),
        "dsr": dsr.get("dsr") if dsr else None, "sr_annual": dsr.get("sr_annual") if dsr else None,
        "skew": round(skew, 3) if skew is not None else None,
        "kurt": round(kurt, 3) if kurt is not None else None,
    }


def split_half_sign(ser):
    s = ser.dropna()
    if len(s) < 8:
        return None
    mid = s.index[len(s) // 2]
    a, b = s[s.index < mid], s[s.index >= mid]
    return {"first": round(float(a.mean()), 5), "second": round(float(b.mean()), 5),
            "sign_agree": bool(np.sign(a.mean()) == np.sign(b.mean()) and a.mean() != 0)}


def era_split_sign(ser, cut="2016-12-01"):
    """Era split at the Shenzhen-Connect segmentation break (prereg §5)."""
    s = ser.dropna()
    pre, post = s[s.index < cut], s[s.index >= cut]
    return {"pre_mean": round(float(pre.mean()), 5) if len(pre) else None, "pre_n": len(pre),
            "post_mean": round(float(post.mean()), 5) if len(post) else None, "post_n": len(post),
            "sign_agree": (bool(np.sign(pre.mean()) == np.sign(post.mean()))
                           if len(pre) and len(post) else None)}


def survivorship_bound(pairs, A_sig, H, hsi, h):
    ndays = {p["h"]: p["n_days"] for p in pairs}
    short5 = sorted(ndays, key=lambda k: ndays[k])[:5]
    deep = [k for k in ndays if ndays[k] >= 12 * 235]     # >=12y (prereg §5)
    def run(cols):
        sub = {k: A_sig[k] for k in cols if k in A_sig}
        rows = build_rebalances(sub, H, hsi, h, min_pairs=min(5, len(sub)))
        ic, icr, top5, ls = eval_signal(rows)
        return {"n_rebal": len(top5.dropna()),
                "top5_mean": round(float(top5.dropna().mean()), 5) if len(top5.dropna()) else None,
                "mean_ic": ic_summary(ic.dropna(), 12).get("mean_ic")}
    excl = [c for c in A_sig if c not in short5]
    return {"exclude_short5": {"dropped": short5, **run(excl)},
            "deep_core_ge12y": ({"names": deep, **run(deep)} if len(deep) >= 5
                                else {"names": deep, "note": "too few deep pairs"})}


def interaction_trial(A_rev_sig, H, hsi, prem_pctile, h=63):
    """Trial c — double-cheap cell: A-washout (rev sig top-tercile) AND H-discount-extreme
    (premium own-pctile top-tercile), vs A-only / H-only / panel. ACCRUE-capped."""
    rows = build_rebalances(A_rev_sig, H, hsi, h, prem_pctile=prem_pctile, min_pairs=MIN_PAIRS)
    cells = {"double": [], "a_only": [], "h_only": [], "panel": []}
    for t, recs in rows:
        tks = list(recs.keys())
        sig = pd.Series({k: recs[k][0] for k in tks})
        fwd = pd.Series({k: recs[k][1] for k in tks})
        pp = pd.Series({k: recs[k][3] for k in tks}).dropna()
        common = sig.index.intersection(pp.index)
        if len(common) < MIN_PAIRS:
            continue
        sig, fwd2, pp = sig[common], fwd[common], pp[common]
        a_hi = sig >= sig.quantile(2 / 3)         # A-washout (rev sig high = washout long)
        h_hi = pp >= pp.quantile(2 / 3)           # H-discount-extreme
        dbl = a_hi & h_hi
        if dbl.sum() >= 1:
            cells["double"].append(float(fwd2[dbl].mean()))
        if a_hi.sum() >= 1:
            cells["a_only"].append(float(fwd2[a_hi].mean()))
        if h_hi.sum() >= 1:
            cells["h_only"].append(float(fwd2[h_hi].mean()))
        cells["panel"].append(float(fwd2.mean()))
    out = {}
    for k, v in cells.items():
        s = pd.Series(v)
        nw = newey_west_tstat(s, lags=2)
        out[k] = {"n": len(s), "mean": nw.get("mean"), "t_hac": nw.get("t"), "p": nw.get("p")}
    return out


def main():
    pairs, A, H, hsi, prem = load()
    print(f"loaded {len(pairs)} pairs; HSI {hsi.index.min().date()}→{hsi.index.max().date()}")

    # A-leg signals, keyed by H-ticker
    A_rev = {tk: own_z(A[tk], R3M) for tk in A}          # trial a: -z applied at rank time
    A_mom = {tk: own_z(A[tk], R1M) for tk in A}          # trial b
    # trial a signal is REVERSAL: deep-negative A 3M return = long → negate the z
    A_rev_long = {tk: -A_rev[tk] for tk in A_rev}
    # C1 controls: H leg's OWN matched trailing return
    H_r3m = {tk: trailing_ret(H[tk], R3M) for tk in H}
    H_r1m = {tk: trailing_ret(H[tk], R1M) for tk in H}
    # premium own-pctile per H-ticker (trial c)
    prem_pct = prem.apply(own_pctile, axis=0)

    out = {"meta": {"n_pairs": len(pairs), "own_win": OWN_WIN, "topn": TOPN,
                    "program_budget": PROGRAM_BUDGET, "family": FAMILY,
                    "hsi_max": str(hsi.index.max().date()),
                    "data_root": str(DATA)}}
    results, pvals = {}, {}

    # ---- trial a: A 3M reversal read-through (PRIMARY) horizons 63 (binding), 21 ----- #
    for h, lbl in [(63, "a_rev_63"), (21, "a_rev_21")]:
        rows = build_rebalances(A_rev_long, H, hsi, h, H_ctrl=(H_r3m if h == 63 else H_r1m))
        ic, icr, top5, ls = eval_signal(rows)
        blk = stats_block(ic, icr, top5, ls, h, lbl)
        blk["split_half"] = split_half_sign(top5)
        blk["era_split"] = era_split_sign(top5)
        results[lbl] = blk
        if blk["top5_p"] is not None:
            pvals[lbl] = blk["top5_p"]
        print(f"[a] h={h}: IC={blk['mean_ic']} t_ic={blk['ic_t_hac']} top5={blk['top5_mean']} "
              f"t={blk['top5_t_hac']} LS_t={blk['ls_t_hac']} DSR={blk['dsr']} n={blk['n_rebal']} "
              f"t_eff={blk['t_eff']} c1_keep={blk['c1_keep_frac']}")

    # ---- trial b: A 1M momentum lead, horizons 21 (binding), 10 --------------------- #
    for h, lbl in [(21, "b_mom_21"), (10, "b_mom_10")]:
        rows = build_rebalances(A_mom, H, hsi, h, H_ctrl=H_r1m)
        ic, icr, top5, ls = eval_signal(rows)
        blk = stats_block(ic, icr, top5, ls, h, lbl)
        blk["split_half"] = split_half_sign(top5)
        blk["era_split"] = era_split_sign(top5)
        results[lbl] = blk
        if blk["top5_p"] is not None:
            pvals[lbl] = blk["top5_p"]
        print(f"[b] h={h}: IC={blk['mean_ic']} t_ic={blk['ic_t_hac']} top5={blk['top5_mean']} "
              f"t={blk['top5_t_hac']} LS_t={blk['ls_t_hac']} DSR={blk['dsr']} n={blk['n_rebal']} "
              f"t_eff={blk['t_eff']} c1_keep={blk['c1_keep_frac']}")

    # ---- trial c: double-cheap interaction (ACCRUE-capped) -------------------------- #
    inter = interaction_trial(A_rev_long, H, hsi, prem_pct, h=63)
    results["c_interaction_63"] = inter
    if inter.get("double", {}).get("p") is not None:
        pvals["c_double_63"] = inter["double"]["p"]
    print(f"[c] double={inter['double']} a_only={inter['a_only']} h_only={inter['h_only']} "
          f"panel={inter['panel']}")

    bh = benjamini_hochberg(pvals, alpha=0.10)
    out["trials"] = results
    out["bh_fdr"] = bh
    out["survivorship_bound_a_rev_63"] = survivorship_bound(pairs, A_rev_long, H, hsi, 63)

    (ROOT / "reports").mkdir(exist_ok=True)
    with open(ROOT / "research/hk_x1_results.json", "w") as f:
        json.dump(out, f, indent=2, default=str)
    print("\nBH-FDR:", {k: v.get("reject") for k, v in bh.items()})
    print("survivorship:", json.dumps(out["survivorship_bound_a_rev_63"], default=str)[:400])
    print("wrote research/hk_x1_results.json")


if __name__ == "__main__":
    main()
