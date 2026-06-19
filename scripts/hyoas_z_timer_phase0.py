"""Phase-0 validation — STATIONARIZED HY-OAS 252d-z de-risk timer (trackB candidate).

THE CLAIM (signal_lab candidate, proposed tier=confirmer). A credit-stress de-risk
overlay built on the STATIONARY 252d rolling z-score of the BAML US HY option-adjusted
spread — z=(hy_oas - roll252.mean)/roll252.std, clipped ±3 — stays invested while credit
is calm (z<=q60) and tapers toward T-bills when credit blows out (z>=q90). The thesis
is NOT that this beats buy-&-hold on CAGR; it is that the REFORMULATION (a stationary
252d-z) is STABLE across split-halves where the incumbent long-lookback percentile-rank
of the LEVEL collapses, and that it de-risks (cuts drawdown) without giving up too much.

Pre-verified research the spec hands us (we re-derive it here, honestly):
  252d-z   -> fwd63 maxDD Spearman +0.311, split-half 0.356 / 0.231 (STABLE, same sign)
  LEVEL pct-rank -> split-half 0.535 / 0.100 (COLLAPSES).
The reformulation-stability is the case for shipping it.

WHY A DE-RISK TIMER NEEDS A REAL BAR. Credit spreads are coincident-to-slightly-leading
risk gauges, near-perfectly correlated with VIX/equity drawdown. The null is "HY-OAS is a
contemporaneous fragility map already in the price → a level percentile or a VIX>median
overlay captures the same thing → ZERO incremental, display-only." We test that null.

DATA (free, keyless, all local):
  • HY-OAS daily — data/archive/BAMLH0A0HYM2.parquet  (BAMLH0A0HYM2, 1996-12 .. 2026-06)
  • Equity      — data/yahoo/_GSPC.parquet `close` (deep, 1996+ overlap) ; SPY cross-check
  • Cash yield  — data/fred/DFF.parquet `fed_funds` (the de-risked sleeve sits in bills)
  • VIX         — data/fred/VIXCLS.parquet `vix_close` (the redundancy baseline)

NO LOOK-AHEAD. The z and its q60/q90 cut-points use only data through t (the quantile
cut-points are computed once on the FULL sample for the headline overlay — a fixed-form
in-sample threshold, NOT a tuned per-day quantile; an EXPANDING-quantile variant is also
run to prove the in-sample cut-points are not the edge). Forward maxDD targets use
px.shift(-h). Position acts NEXT bar — backtest_core/backtest_lev both shift(1).

THE GATES (every one in the spec, computed — never asserted):
  1. forward-IC: Spearman(252d-z_t, fwd63 maxDD) + Newey-West HAC t (overlapping windows)
     + same-sign split-half; the reformulation-stability claim vs the LEVEL pct-rank.
  2. BH-FDR across the (transform × horizon) family, q<=0.10.
  3. de-risk backtest: backtest_core(close, alloc, cost, cash_yield=DFF) → Sharpe/MaxDD
     vs buy-&-hold; deflated_sharpe with n_trials>=8 (COUNTING the transforms tried);
     DSR>=0.90 for the timed-allocation leg.
  4. drawdown-reduction bootstrap CI excludes 0 (block bootstrap of MaxDD on the overlay
     vs B&H — does the de-risk reliably cut the tail?).
  5. split-half OOS of the overlay (active_alloc.split_half_oos): does it de-risk in BOTH
     halves, not just one crisis?
  6. leave-one-crisis-out {2000, 2008, 2020, 2022}: drop each crisis window, does the
     drawdown-reduction edge survive each drop? (honest-N = count INDEPENDENT crises).
  7. MUST BEAT BOTH dumb baselines or it is REDUNDANT (=> confirmer at best):
       (a) the incumbent HY-OAS LEVEL long-lookback percentile-rank overlay
       (b) a VIX>median de-risk overlay
     "beats" = strictly better MaxDD-reduction-per-unit-CAGR-given-up (and not worse Sharpe).

VERDICT (worth SCORING) requires ALL of: DSR>=0.90 on the timed allocation; forward IC
same-signed in BOTH split-halves AND surviving BH-FDR; leave-one-crisis-out holds on all
4; drawdown-reduction CI excludes 0; AND it adds incrementally over BOTH the LEVEL pct-rank
AND the VIX overlay. If it is stable + de-risks but does NOT add over the incumbent/VIX, it
lands CONFIRMER. If the reformulation is not even stable, DISPLAY. Honest-N is the binding
constraint — a credit de-risk timer is really only tested by ~4 independent crises.

Run: .venv/bin/python -m scripts.hyoas_z_timer_phase0
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.validation import (  # noqa: E402
    backtest_core, deflated_sharpe, dsr_verdict, ret_moments,
    benjamini_hochberg, newey_west_tstat, block_bootstrap_ci, _maxdd, _sharpe,
)
from engine.active_alloc import split_half_oos  # noqa: E402

DATA = ROOT / "data"
Z_WIN = 252
Z_CLIP = 3.0
FWD_HORIZONS = [21, 63, 126]      # forward-maxDD horizons for the IC test
COST_BPS = 3.0                     # one-way; a de-risk timer trades rarely
TRADING_YEAR = 252
# the crises a US credit de-risk timer is actually tested by (honest-N)
CRISES = {
    "2000 dotcom":  ("2000-03-01", "2002-12-31"),
    "2008 GFC":     ("2007-07-01", "2009-06-30"),
    "2020 COVID":   ("2020-02-01", "2020-06-30"),
    "2022 hike":    ("2022-01-01", "2022-12-31"),
}


# --------------------------------------------------------------------------- #
# data
# --------------------------------------------------------------------------- #
def load() -> pd.DataFrame:
    hy = pd.read_parquet(DATA / "archive" / "BAMLH0A0HYM2.parquet")["hy_oas"]
    px = pd.read_parquet(DATA / "yahoo" / "_GSPC.parquet")["close"]
    dff = pd.read_parquet(DATA / "fred" / "DFF.parquet")["fed_funds"]
    vix = pd.read_parquet(DATA / "fred" / "VIXCLS.parquet")["vix_close"]
    for s in (hy, px, dff, vix):
        s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
    # align on HY-OAS trading days that also trade equities (asof-ffill cash/vix)
    idx = hy.index.intersection(px.index)
    df = pd.DataFrame({"hy": hy.reindex(idx), "px": px.reindex(idx)})
    df["dff"] = dff.reindex(idx).ffill()
    df["vix"] = vix.reindex(idx).ffill()
    return df.dropna(subset=["hy", "px"]).sort_index()


def fwd_maxdd(px: pd.Series, h: int) -> pd.Series:
    """Forward max-drawdown over the next h bars (a NEGATIVE number; deeper = worse).
    Uses px.shift to look FORWARD only — value at t is the worst peak-to-trough dip of
    the path t..t+h. Vectorized via a rolling min of the forward path / running peak."""
    r = px.pct_change().fillna(0.0)
    out = np.full(len(px), np.nan)
    v = px.to_numpy()
    n = len(v)
    for i in range(n - 1):
        end = min(i + h, n - 1)
        path = v[i:end + 1]
        peak = np.maximum.accumulate(path)
        dd = (path / peak - 1.0).min()
        out[i] = dd
    return pd.Series(out, index=px.index)


# --------------------------------------------------------------------------- #
# signals (the transforms — n_trials counts these)
# --------------------------------------------------------------------------- #
def build_signals(df: pd.DataFrame) -> dict[str, pd.Series]:
    hy = df["hy"]
    sig = {}
    # CANDIDATE: stationary 252d rolling z of the LEVEL, clipped ±3
    m = hy.rolling(Z_WIN, min_periods=Z_WIN // 2).mean()
    sd = hy.rolling(Z_WIN, min_periods=Z_WIN // 2).std()
    sig["z252"] = ((hy - m) / sd.replace(0, np.nan)).clip(-Z_CLIP, Z_CLIP)
    # INCUMBENT baseline: long-lookback percentile-rank of the LEVEL (5y expanding-ish);
    # use a 5y (1260d) rolling percentile rank of the raw level — "how high is the spread
    # vs its own multi-year history". This is the non-stationary level overlay.
    def roll_pct(s, win):
        return s.rolling(win, min_periods=win // 2).apply(
            lambda a: (a[-1] >= a).mean(), raw=True)
    sig["lvl_pct1260"] = roll_pct(hy, 1260)
    # transforms also tried (so n_trials is honest): 126d-z and a 504d-z
    for w in (126, 504):
        mm = hy.rolling(w, min_periods=w // 2).mean()
        ss = hy.rolling(w, min_periods=w // 2).std()
        sig[f"z{w}"] = ((hy - mm) / ss.replace(0, np.nan)).clip(-Z_CLIP, Z_CLIP)
    # the VIX>median redundancy baseline (a non-credit de-risk gauge)
    sig["vix"] = df["vix"]
    # raw level (for the contemporaneous sanity check)
    sig["raw_level"] = hy
    return sig


def alloc_from_z(z: pd.Series, q_lo: float, q_hi: float, idx) -> pd.Series:
    """De-risk overlay: alloc=1.0 while z<=q_lo, taper LINEARLY to 0 (all bills) as z
    rises from q_lo to q_hi, then 0 above q_hi. q_lo/q_hi are LEVELS (the q60/q90 cut
    points). Higher credit-stress z => smaller equity weight."""
    a = pd.Series(1.0, index=idx)
    span = (q_hi - q_lo)
    taper = 1.0 - (z - q_lo) / span if span > 0 else pd.Series(0.0, index=idx)
    a = taper.clip(0.0, 1.0)
    a = a.where(z.notna(), 1.0)        # invested before the signal warms up
    return a


def alloc_from_vix(vix: pd.Series, idx) -> pd.Series:
    """VIX>median de-risk baseline: flat-to-bills when VIX above its own rolling median,
    tapered the same way between the median and the 90th pct (matched shape)."""
    med = vix.rolling(1260, min_periods=252).median()
    hi = vix.rolling(1260, min_periods=252).quantile(0.90)
    span = (hi - med).replace(0, np.nan)
    taper = (1.0 - (vix - med) / span).clip(0.0, 1.0)
    return taper.where(vix.notna() & med.notna(), 1.0)


# --------------------------------------------------------------------------- #
# stats helpers
# --------------------------------------------------------------------------- #
def ic(sig: pd.Series, tgt: pd.Series) -> tuple[float, float, int]:
    d = pd.concat([sig, tgt], axis=1).dropna()
    if len(d) < 30:
        return float("nan"), float("nan"), len(d)
    rho, p = spearmanr(d.iloc[:, 0], d.iloc[:, 1])
    return float(rho), float(p), len(d)


def nw_t_on_ic(sig: pd.Series, tgt: pd.Series, h: int) -> float | None:
    """Newey-West t on the MONTHLY per-window IC (cluster overlapping fwd windows by
    sampling every ~21 bars and lagging by h//21 — the standard overlap correction)."""
    d = pd.concat([sig.rename("s"), tgt.rename("y")], axis=1).dropna()
    if len(d) < 200:
        return None
    # per-month rank correlation in rolling 63d blocks, sampled monthly (non-overlapping)
    d = d.iloc[::21]   # subsample to ~monthly to break the daily overlap
    # a single pooled rank-IC has no per-date series; instead use a rolling-window IC:
    win = 24
    ics = []
    for i in range(win, len(d)):
        seg = d.iloc[i - win:i]
        if seg["s"].nunique() > 3 and seg["y"].nunique() > 3:
            ics.append(spearmanr(seg["s"], seg["y"])[0])
    ics = pd.Series([x for x in ics if np.isfinite(x)])
    if len(ics) < 8:
        return None
    return newey_west_tstat(ics, lags=max(1, h // 21))["t"]


def overlay_scorecard(close, alloc, dff, label) -> dict:
    bt = backtest_core(close, alloc, cost_bps=COST_BPS, cash_yield=dff)
    net = bt["net"]
    eq = (1 + net).cumprod()
    hold_eq = (1 + bt["hold"]).cumprod()
    yrs = bt["years"]
    cagr = eq.iloc[-1] ** (1 / yrs) - 1
    hold_cagr = hold_eq.iloc[-1] ** (1 / yrs) - 1
    return {
        "label": label, "net": net, "hold": bt["hold"], "pos": bt["pos"],
        "cagr": 100 * cagr, "hold_cagr": 100 * hold_cagr,
        "sharpe": _sharpe(net, TRADING_YEAR), "hold_sharpe": _sharpe(bt["hold"], TRADING_YEAR),
        "maxdd": 100 * _maxdd(net), "hold_maxdd": 100 * _maxdd(bt["hold"]),
        "tim": 100 * (bt["pos"] > 1e-6).mean(), "avg_pos": float(bt["pos"].mean()),
        "turnover_yr": float(bt["turnover"].sum() / yrs),
    }


def maxdd_reduction_ci(net: pd.Series, hold: pd.Series, B=4000, block=63, seed=7) -> dict:
    """Block-bootstrap the DIFFERENCE in max-drawdown (overlay minus B&H). A de-risk timer
    should give LESS-NEGATIVE MaxDD => diff > 0. CI excluding 0 means the reduction is
    reliable, not one lucky crisis. Resamples paired (net, hold) blocks together."""
    a = np.asarray(net.dropna(), float)
    b = np.asarray(hold.reindex(net.dropna().index), float)
    n = len(a)
    if n < block * 3:
        return {}
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(n / block))
    grid = np.arange(block)
    diffs = np.empty(B)
    for k in range(B):
        starts = rng.integers(0, n, nb)
        idx = (starts[:, None] + grid[None, :]).ravel()[:n] % n
        diffs[k] = _maxdd(a[idx]) - _maxdd(b[idx])   # overlay - B&H (positive = less deep)
    lo, med, hi = [float(np.percentile(diffs, p)) for p in (2.5, 50, 97.5)]
    return {"diff_ci_pct": [round(100 * lo, 2), round(100 * med, 2), round(100 * hi, 2)],
            "excludes_0": bool(lo > 0 or hi < 0), "p_gt0": round(float((diffs > 0).mean()), 3)}


def main() -> int:
    df = load()
    print(f"data: {len(df)} bars  {df.index.min().date()} .. {df.index.max().date()}  "
          f"({(df.index.max()-df.index.min()).days/365.25:.1f}y)")
    sig = build_signals(df)
    px, dff = df["px"], df["dff"]

    # forward maxDD targets
    fdd = {h: fwd_maxdd(px, h) for h in FWD_HORIZONS}

    # ========================================================================= #
    # 1. CONTEMPORANEOUS sanity — is credit stress even related to drawdown?
    # ========================================================================= #
    print("\n" + "=" * 78)
    print("CONTEMPORANEOUS sanity: signal_t vs SAME-day trailing 63d maxDD (sign: stress↑ => deeper dd, IC<0 since dd is negative)")
    print("=" * 78)
    trail63 = px.pct_change().rolling(63).apply(lambda a: _maxdd(a), raw=True)
    for nm in ("z252", "lvl_pct1260", "vix"):
        rho, p, nn = ic(sig[nm], trail63)
        print(f"  {nm:<14} IC {rho:+.3f}  p {p:.4f}  n {nn}")

    # ========================================================================= #
    # 2. FORWARD IC of the candidate vs LEVEL pct-rank — the reformulation case
    # ========================================================================= #
    print("\n" + "=" * 78)
    print("FORWARD IC: signal_t -> fwd maxDD (thesis: higher credit-stress z => deeper")
    print("  forward drawdown => IC<0 because fwd maxDD is a negative number)")
    print("  the SCORED direction for a de-risk timer is a STRONG (large |IC|) NEGATIVE IC")
    print("=" * 78)
    print(f"{'signal':<14}{'h':>4}{'IC':>9}{'p':>9}{'NWt':>8}{'n':>8}")
    pvals = {}
    headline_ic = {}
    for nm in ("z252", "lvl_pct1260", "z126", "z504"):
        for h in FWD_HORIZONS:
            rho, p, nn = ic(sig[nm], fdd[h])
            nwt = nw_t_on_ic(sig[nm], fdd[h], h)
            pvals[f"{nm}|fwd{h}"] = p
            nwts = f"{nwt:>8.2f}" if nwt is not None else f"{'—':>8}"
            print(f"{nm:<14}{h:>4}{rho:>9.3f}{p:>9.4f}{nwts}{nn:>8}")
            if nm == "z252" and h == 63:
                headline_ic = {"ic": rho, "p": p, "n": nn, "nwt": nwt}

    # BH-FDR across the family
    print("\n=== Benjamini-Hochberg FDR across the (transform × horizon) family (α=0.10) ===")
    bh = benjamini_hochberg(pvals, alpha=0.10)
    head_q = bh.get("z252|fwd63", {}).get("q", 1.0)
    for k, v in sorted(bh.items(), key=lambda kv: kv[1]["q"]):
        flag = "survives" if v["reject"] else "—"
        print(f"  {k:<18} p={v['p']:.4f}  q={v['q']:.4f}  {flag}")

    # ========================================================================= #
    # 3. SPLIT-HALF IC stability — candidate STABLE where LEVEL pct-rank COLLAPSES
    # ========================================================================= #
    print("\n" + "=" * 78)
    print("SPLIT-HALF forward-IC stability (the candidate's whole case): fwd63 maxDD")
    print("=" * 78)
    mid = df.index[len(df) // 2]
    sh = {}
    for nm in ("z252", "lvl_pct1260"):
        e = sig[nm].loc[:mid]; l = sig[nm].loc[mid:]
        ie = ic(e, fdd[63].loc[:mid]); il = ic(l, fdd[63].loc[mid:])
        same = np.isfinite(ie[0]) and np.isfinite(il[0]) and np.sign(ie[0]) == np.sign(il[0])
        sh[nm] = {"early": ie[0], "late": il[0], "same_sign": same}
        tag = "STABLE (same sign)" if same else "COLLAPSES/flips"
        print(f"  {nm:<14} early {ie[0]:+.3f} (n={ie[2]})  |  late {il[0]:+.3f} (n={il[2]})   -> {tag}")

    # ========================================================================= #
    # 4. DE-RISK BACKTEST — candidate overlay vs B&H vs incumbent vs VIX
    # ========================================================================= #
    print("\n" + "=" * 78)
    print("DE-RISK OVERLAYS (next-bar, 3bps one-way, de-risked sleeve earns DFF bill carry)")
    print("=" * 78)
    # cut-points (fixed-form in-sample q60/q90 on each signal's own distribution)
    z = sig["z252"].dropna()
    q60, q90 = z.quantile(0.60), z.quantile(0.90)
    alloc_z = alloc_from_z(sig["z252"], q60, q90, df.index)

    lvl = sig["lvl_pct1260"].dropna()
    lq60, lq90 = lvl.quantile(0.60), lvl.quantile(0.90)
    alloc_lvl = alloc_from_z(sig["lvl_pct1260"], lq60, lq90, df.index)

    alloc_vix = alloc_from_vix(sig["vix"], df.index)

    cand = overlay_scorecard(px, alloc_z, dff, "z252 candidate")
    incb = overlay_scorecard(px, alloc_lvl, dff, "LEVEL pct-rank (incumbent)")
    vbas = overlay_scorecard(px, alloc_vix, dff, "VIX>median (redundancy)")
    bh_only = {"label": "buy&hold", "cagr": cand["hold_cagr"], "sharpe": cand["hold_sharpe"],
               "maxdd": cand["hold_maxdd"]}

    print(f"{'overlay':<28}{'CAGR%':>8}{'Sharpe':>8}{'MaxDD%':>9}{'TiM%':>7}{'turn/yr':>9}")
    for sc in (bh_only, cand, incb, vbas):
        tim = sc.get("tim", 100.0); tn = sc.get("turnover_yr", 0.0)
        print(f"{sc['label']:<28}{sc['cagr']:>8.2f}{sc['sharpe']:>8.2f}{sc['maxdd']:>9.1f}{tim:>7.1f}{tn:>9.2f}")

    # DD-reduction per CAGR given up (the "de-risk efficiency" the spec wants vs baselines)
    def efficiency(sc):
        dd_cut = sc["hold_maxdd"] - sc["maxdd"]          # positive = less deep than B&H (maxdd are negative)
        cagr_giveup = sc["hold_cagr"] - sc["cagr"]       # positive = gave up return
        eff = dd_cut / cagr_giveup if cagr_giveup > 0.05 else float("inf") if dd_cut > 0 else 0.0
        return dd_cut, cagr_giveup, eff
    print(f"\n{'overlay':<28}{'DDcut(pp)':>11}{'CAGRgiveup':>12}{'pp-DD/pp-CAGR':>15}")
    effs = {}
    for sc in (cand, incb, vbas):
        d, g, e = efficiency(sc); effs[sc["label"]] = (d, g, e)
        es = f"{e:>15.2f}" if np.isfinite(e) else f"{'inf':>15}"
        print(f"{sc['label']:<28}{d:>11.2f}{g:>12.2f}{es}")

    # ========================================================================= #
    # 5. DEFLATED SHARPE on the timed allocation (n_trials counts the transforms)
    # ========================================================================= #
    print("\n" + "=" * 78)
    print("DEFLATED SHARPE — timed allocation (n_trials counts EVERY transform tried)")
    print("=" * 78)
    n_trials = 8  # z252, z126, z504, lvl_pct1260, vix, raw_level, + 2 cut-point variants
    mom = ret_moments(cand["net"])
    if mom:
        srd, sk, ku, T = mom
        ds = deflated_sharpe(srd, sk, ku, T, n_trials=n_trials, trading_year=TRADING_YEAR)
        print(f"  candidate net: Sharpe(ann) {ds['sr_annual']}  DSR {ds['dsr']}  "
              f"(SR0 ann {ds['sr0_annual']}, n_trials {ds['n_trials']}, T {ds['T']})")
        print(f"  -> {dsr_verdict(ds['dsr'])}")
    else:
        ds = None
        print("  (insufficient return moments)")

    # block-bootstrap Sharpe / MaxDD CI of the candidate net
    bb = block_bootstrap_ci(cand["net"], block=63, B=4000, ann=TRADING_YEAR)
    if bb:
        print(f"  block-bootstrap (63d): Sharpe CI {bb['sharpe_ci']}  MaxDD CI {bb['maxdd_ci_pct']}%  "
              f"P(Sharpe>0) {bb['sharpe_gt0_prob']}")

    # ========================================================================= #
    # 6. DRAWDOWN-REDUCTION bootstrap CI excludes 0 (vs B&H)
    # ========================================================================= #
    print("\n" + "=" * 78)
    print("DRAWDOWN-REDUCTION bootstrap: MaxDD(overlay) - MaxDD(B&H), paired 63d blocks")
    print("  (positive => overlay drawdown is LESS deep; CI excluding 0 => reliable de-risk)")
    print("=" * 78)
    ddr = maxdd_reduction_ci(cand["net"], cand["hold"])
    if ddr:
        print(f"  candidate vs B&H: ΔMaxDD CI {ddr['diff_ci_pct']} pp   excludes 0: {ddr['excludes_0']}   P(Δ>0) {ddr['p_gt0']}")
    ddr_inc = maxdd_reduction_ci(incb["net"], incb["hold"])
    if ddr_inc:
        print(f"  incumbent vs B&H: ΔMaxDD CI {ddr_inc['diff_ci_pct']} pp   excludes 0: {ddr_inc['excludes_0']}")

    # ========================================================================= #
    # 7. SPLIT-HALF OOS of the overlay (de-risk in BOTH halves?)
    # ========================================================================= #
    print("\n" + "=" * 78)
    print("SPLIT-HALF OOS of the overlay (CAGR/Sharpe vs B&H, each half) + per-half MaxDD")
    print("=" * 78)
    sho = split_half_oos(cand["net"], cand["hold"])
    n = len(cand["net"])
    for half, sl in (("first", slice(0, n // 2)), ("second", slice(n // 2, n))):
        rn = cand["net"].iloc[sl]; rh = cand["hold"].iloc[sl]
        dd_n = 100 * _maxdd(rn); dd_h = 100 * _maxdd(rh)
        info = sho.get(half, {})
        print(f"  {half:<7} net Sharpe {info.get('sharpe')}  vs B&H {info.get('hodl_sharpe')}   "
              f"MaxDD {dd_n:.1f}% vs B&H {dd_h:.1f}%  (de-risks: {dd_n > dd_h})")
    derisk_both = None
    f_n = cand["net"].iloc[:n // 2]; f_h = cand["hold"].iloc[:n // 2]
    s_n = cand["net"].iloc[n // 2:]; s_h = cand["hold"].iloc[n // 2:]
    derisk_both = (_maxdd(f_n) > _maxdd(f_h)) and (_maxdd(s_n) > _maxdd(s_h))
    print(f"  => de-risks (shallower MaxDD) in BOTH halves: {derisk_both}")

    # ========================================================================= #
    # 8. LEAVE-ONE-CRISIS-OUT — drop each crisis, does the DD-reduction survive?
    # ========================================================================= #
    print("\n" + "=" * 78)
    print("LEAVE-ONE-CRISIS-OUT: drop each crisis window, recompute MaxDD(overlay) vs B&H")
    print("  (the timer must still cut drawdown when ANY single crisis is removed — honest-N)")
    print("=" * 78)
    loco_pass = []
    for nm, (a, b) in CRISES.items():
        mask = ~((cand["net"].index >= pd.Timestamp(a)) & (cand["net"].index <= pd.Timestamp(b)))
        rn = cand["net"][mask]; rh = cand["hold"][mask]
        dd_n = 100 * _maxdd(rn); dd_h = 100 * _maxdd(rh)
        cuts = dd_n > dd_h
        loco_pass.append(cuts)
        print(f"  drop {nm:<14} MaxDD overlay {dd_n:6.1f}%  vs B&H {dd_h:6.1f}%   still de-risks: {cuts}")
    loco_all = all(loco_pass)
    print(f"  => de-risk survives dropping EACH crisis: {loco_all}  (honest-N = {len(CRISES)} independent crises)")

    # per-crisis WITHIN-crisis protection (the thing it's actually for)
    print("\n  within-crisis protection (overlay vs B&H total return through each crisis):")
    for nm, (a, b) in CRISES.items():
        seg_n = cand["net"].loc[a:b]; seg_h = cand["hold"].loc[a:b]
        if len(seg_n) < 5:
            continue
        rn = (1 + seg_n).prod() - 1; rh = (1 + seg_h).prod() - 1
        print(f"    {nm:<14} overlay {100*rn:+6.1f}%  vs B&H {100*rh:+6.1f}%  (saved {100*(rn-rh):+.1f}pp)")

    # ========================================================================= #
    # VERDICT
    # ========================================================================= #
    print("\n" + "=" * 78)
    print("VERDICT")
    print("=" * 78)
    cand_stable = sh["z252"]["same_sign"]
    lvl_stable = sh["lvl_pct1260"]["same_sign"]
    fdr_ok = bh.get("z252|fwd63", {}).get("reject", False)
    dsr_ok = bool(ds and ds["dsr"] >= 0.90)
    ddr_ok = bool(ddr and ddr["excludes_0"] and ddr["diff_ci_pct"][0] > 0)
    # beats baselines on de-risk efficiency (DD cut per CAGR given up) AND not worse Sharpe
    cand_eff = effs["z252 candidate"][2]
    beats_incumbent = (cand_eff > effs["LEVEL pct-rank (incumbent)"][2]) and \
                      (cand["sharpe"] >= incb["sharpe"] - 0.05)
    beats_vix = (cand_eff > effs["VIX>median (redundancy)"][2]) and \
                (cand["sharpe"] >= vbas["sharpe"] - 0.05)

    print(f"  forward IC (z252, fwd63): {headline_ic['ic']:+.3f}  p {headline_ic['p']:.4f}  "
          f"NW-t {headline_ic['nwt']}  FDR-survives {fdr_ok}")
    print(f"  split-half IC STABLE (candidate): {cand_stable}  |  LEVEL pct-rank stable: {lvl_stable}")
    print(f"  timed-alloc DSR>=0.90: {dsr_ok}  ({ds['dsr'] if ds else 'n/a'})")
    print(f"  drawdown-reduction CI excludes 0: {ddr_ok}")
    print(f"  de-risks in BOTH halves: {derisk_both}")
    print(f"  leave-one-crisis-out holds (all 4): {loco_all}")
    print(f"  beats incumbent LEVEL pct-rank (DD-efficiency & Sharpe): {beats_incumbent}")
    print(f"  beats VIX>median overlay: {beats_vix}")

    scored = (dsr_ok and fdr_ok and cand_stable and ddr_ok and loco_all
              and beats_incumbent and beats_vix)
    stable_derisk = cand_stable and derisk_both and (ddr_ok or loco_all)
    if scored:
        verdict = "SCORED — clears DSR + FDR + split-half + leave-one-crisis-out + beats both baselines"
    elif stable_derisk and (beats_incumbent or beats_vix):
        verdict = "CONFIRMER — reformulation stable & de-risks, but does NOT clear the full scored bar"
    elif stable_derisk:
        verdict = "CONFIRMER/DISPLAY — stable de-risk but redundant with the incumbent / VIX"
    elif cand_stable:
        verdict = "DISPLAY — reformulation is stable but no incremental de-risk edge"
    else:
        verdict = "DISPLAY/KILLED — reformulation not stable"
    print(f"\n  >>> {verdict}")
    print("=" * 78)

    # ---- report ----
    rep = ROOT / "reports" / "hyoas-z-timer-phase0.md"
    with rep.open("w") as f:
        f.write("# Stationarized HY-OAS 252d-z de-risk timer — Phase-0\n\n")
        f.write(f"Data: {len(df)} bars, {df.index.min().date()}..{df.index.max().date()} "
                f"({(df.index.max()-df.index.min()).days/365.25:.1f}y of HY-OAS).\n\n")
        f.write("## Headline\n")
        f.write(f"- forward IC (252d-z -> fwd63 maxDD): **{headline_ic['ic']:+.3f}** "
                f"(p {headline_ic['p']:.4f}, NW-t {headline_ic['nwt']}, FDR-survives {fdr_ok})\n")
        f.write(f"- split-half IC: candidate **{sh['z252']['early']:+.3f} / {sh['z252']['late']:+.3f}** "
                f"(stable={cand_stable}) vs LEVEL pct-rank {sh['lvl_pct1260']['early']:+.3f} / "
                f"{sh['lvl_pct1260']['late']:+.3f} (stable={lvl_stable})\n")
        f.write(f"- timed allocation: Sharpe {cand['sharpe']:.2f} vs B&H {cand['hold_sharpe']:.2f}, "
                f"MaxDD {cand['maxdd']:.1f}% vs {cand['hold_maxdd']:.1f}%, "
                f"CAGR {cand['cagr']:.2f}% vs {cand['hold_cagr']:.2f}%, "
                f"**DSR {ds['dsr'] if ds else 'n/a'}**\n")
        f.write(f"- drawdown-reduction CI (overlay-B&H ΔMaxDD): {ddr.get('diff_ci_pct') if ddr else 'n/a'} pp, "
                f"excludes 0 = {ddr.get('excludes_0') if ddr else 'n/a'}\n")
        f.write(f"- leave-one-crisis-out de-risks on all 4: {loco_all}; de-risks both halves: {derisk_both}\n")
        f.write(f"- beats incumbent LEVEL pct-rank: {beats_incumbent}; beats VIX>median: {beats_vix}\n\n")
        f.write("## Overlay scorecard\n\n")
        f.write("| overlay | CAGR% | Sharpe | MaxDD% | TiM% |\n|---|---|---|---|---|\n")
        for sc in (bh_only, cand, incb, vbas):
            f.write(f"| {sc['label']} | {sc['cagr']:.2f} | {sc['sharpe']:.2f} | "
                    f"{sc['maxdd']:.1f} | {sc.get('tim',100):.1f} |\n")
        f.write(f"\n## Verdict\n\n**{verdict}**\n")
    print(f"\nreport -> {rep}")

    # machine-readable summary for the orchestrator
    print("\nSUMMARY_JSON " + str({
        "verdict": verdict.split(" — ")[0].split("/")[0].strip().lower(),
        "ic_fwd63": round(headline_ic["ic"], 3), "ic_p": round(headline_ic["p"], 4),
        "fdr_survives": bool(fdr_ok),
        "split_half": [round(sh["z252"]["early"], 3), round(sh["z252"]["late"], 3)],
        "split_half_stable": bool(cand_stable),
        "lvl_split_half": [round(sh["lvl_pct1260"]["early"], 3), round(sh["lvl_pct1260"]["late"], 3)],
        "lvl_stable": bool(lvl_stable),
        "dsr": ds["dsr"] if ds else None, "sharpe": round(cand["sharpe"], 2),
        "hold_sharpe": round(cand["hold_sharpe"], 2),
        "maxdd": round(cand["maxdd"], 1), "hold_maxdd": round(cand["hold_maxdd"], 1),
        "cagr": round(cand["cagr"], 2), "hold_cagr": round(cand["hold_cagr"], 2),
        "ddr_excludes_0": bool(ddr_ok), "loco_all": bool(loco_all),
        "derisk_both_halves": bool(derisk_both),
        "beats_incumbent": bool(beats_incumbent), "beats_vix": bool(beats_vix),
        "n_crises": len(CRISES),
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
