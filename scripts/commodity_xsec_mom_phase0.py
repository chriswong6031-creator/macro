"""Phase-0: CROSS-SECTIONAL COMMODITY MOMENTUM (19-asset, deep) — READ-ONLY research.

The candidate. A CROSS-SECTIONAL momentum long/short on a properly diversified
19-commodity continuous front-month cross-section (the classic Gorton-Rouwenhorst /
Moskowitz-Ooi-Pedersen / Erb-Harvey commodity-momentum factor), vs the prior 5-leg
TIME-SERIES book that landed CONFIRMER at DSR 0.68.

Universe (yfinance auto_adjust=True, period max ~2000-2026):
  metals     GC=F SI=F HG=F PL=F PA=F          (gold silver copper platinum palladium)
  energy     CL=F BZ=F NG=F HO=F RB=F          (WTI brent natgas heating-oil rbob)
  grains     ZC=F ZS=F ZW=F                    (corn soybean wheat)
  softs      KC=F CT=F SB=F CC=F               (coffee cotton sugar cocoa)
  livestock  LE=F HE=F                         (live-cattle lean-hogs)

Signal (per month, per commodity), cross-sectionally ranked:
  mom_12_1 = px.shift(SKIP)/px.shift(LB) - 1        # 12-1m (classic, headline)
  also test mom_12 (no skip) and mom_1 (1m reversal)
Each rebal: rank cross-section, LONG top tercile / SHORT bottom tercile, equal-weight,
then VOL-TARGET the whole book to ~10%/yr (scale by trailing book vol). Position acts
NEXT bar (shift 1, no look-ahead); 8-10bps one-way turnover cost.

The honest bar (SCORED requires ALL of):
  * forward rank-IC (xsec mom vs fwd 21d return) per month surviving BH-FDR q<=0.10
  * tercile L/S DSR>=0.90 (>=0.95 'survives') net of ~8-10bps one-way, over the
    (lookback x rebal) trial grid (HONEST n_trials)
  * same-sign split-half
  * leave-one-crisis-out {2008, 2014-16 oil bust, 2020, 2022}
  * beats the DUMB baselines: EW-long-commodity B&H AND a per-commodity 200dma long/flat
  * honest-N: ~19 commodities is a THIN cross-section; months autocorrelate -> count
    INDEPENDENT regimes, not raw rebals

No look-ahead: signal uses data through t; position acts next bar (shift); forward
target = px.shift(-h). Data cached to data/commodity_xsec/closes.parquet for instant re-runs.

Run:  ./.venv/bin/python3 scripts/commodity_xsec_mom_phase0.py
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from engine.validation import (  # noqa: E402
    backtest_core, ret_moments, deflated_sharpe, dsr_verdict,
    block_bootstrap_ci, purged_folds, _maxdd, _sharpe,
    rank_ic, ic_summary, benjamini_hochberg, newey_west_tstat,
)

# ---------------------------------------------------------------- config (the SPEC)
TICKERS: dict[str, str] = {
    "GC=F": "gold",   "SI=F": "silver",   "HG=F": "copper",  "PL=F": "platinum",
    "PA=F": "palladium", "CL=F": "wti",   "BZ=F": "brent",   "NG=F": "natgas",
    "HO=F": "heatoil", "RB=F": "rbob",    "ZC=F": "corn",    "ZS=F": "soybean",
    "ZW=F": "wheat",   "KC=F": "coffee",  "CT=F": "cotton",  "SB=F": "sugar",
    "CC=F": "cocoa",   "LE=F": "cattle",  "HE=F": "hogs",
}
DATA_DIR = ROOT / "data" / "commodity_xsec"
CACHE = DATA_DIR / "closes.parquet"

LB = 252            # 12-month lookback
SKIP = 21           # drop the recent 1 month -> 12-1m trend
REBAL = 21          # monthly rebalance (~21 trading days)
TARGET_VOL = 0.10   # vol target the book to ~10%/yr (the SPEC)
VOL_WIN = 63        # trailing book-vol window for the vol-target
COST_BPS = 9.0      # one-way turnover cost (8-10bps; midpoint)
FWD_H = 21          # forward horizon for rank-IC
MIN_NAMES = 9       # need a real cross-section each rebal (tercile L+S)
ANN = 252
START = "2002-01-01"  # all-or-most legs warm (252+63 from ~2000-2001 listings); BZ=F from 2007

# the (lookback x rebal) grid we TRY -> honest DSR trial count
LB_GRID = [(126, 21), (252, 21), (252, 0), (21, 0)]   # 6-1, 12-1, 12m, 1m(reversal)
REBAL_GRID = [5, 10, 21]
HEADLINE_LB = (LB, SKIP)

# independent crisis clusters (commodity-relevant): the SPEC's {2008,2014-16,2020,2022}
CRISES = [
    ("2008 GFC",         "2008-06-01", "2009-03-31"),
    ("2014-16 oil bust", "2014-07-01", "2016-02-29"),
    ("2020 COVID",       "2020-01-15", "2020-04-30"),
    ("2022 bear",        "2022-01-01", "2022-12-31"),
]


# ---------------------------------------------------------------- data collection
def collect() -> pd.DataFrame:
    """Fetch 19-commodity adjusted front-month closes via yfinance; cache to parquet."""
    if CACHE.exists():
        px = pd.read_parquet(CACHE)
        px.index = pd.to_datetime(px.index)
        return px
    import yfinance as yf
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    cols = {}
    for tk, nm in TICKERS.items():
        try:
            df = yf.download(tk, period="max", auto_adjust=True, progress=False,
                             threads=False)
            if df is None or df.empty:
                print(f"  [skip] {nm} ({tk}) — empty")
                continue
            s = df["Close"]
            if isinstance(s, pd.DataFrame):
                s = s.iloc[:, 0]
            cols[nm] = s.rename(nm)
            print(f"  [ok]  {nm:<10} ({tk})  {s.index.min().date()}..{s.index.max().date()}  "
                  f"n={s.notna().sum()}")
        except Exception as e:
            print(f"  [err] {nm} ({tk}) — {e}")
    px = pd.DataFrame(cols).sort_index()
    px.index = pd.to_datetime(px.index)
    px = px[~px.index.duplicated(keep="last")].dropna(how="all")
    px.to_parquet(CACHE)
    print(f"  [cached] {CACHE}  shape={px.shape}")
    return px


# ---------------------------------------------------------------- signals / book
def xsec_mom(px: pd.DataFrame, lb: int, skip: int) -> pd.DataFrame:
    """Cross-sectional momentum signal (trailing return, recent `skip` dropped)."""
    if skip > 0:
        return px.shift(skip) / px.shift(lb) - 1.0
    return px / px.shift(lb) - 1.0


def tercile_weights(sig: pd.DataFrame, rebal: int, min_names: int = MIN_NAMES) -> pd.DataFrame:
    """Each rebal date: cross-sectionally rank the signal, LONG top tercile /
    SHORT bottom tercile, equal-weight, dollar-neutral. Held flat between rebals.
    Returns a daily weight frame (pre next-bar lag)."""
    idx = sig.index
    rebal_dates = idx[::rebal]
    # build target weights only ON rebal dates (NaN elsewhere -> ffill holds the book)
    W = pd.DataFrame(np.nan, index=idx, columns=sig.columns)
    for d in rebal_dates:
        row = sig.loc[d].dropna()
        if len(row) < min_names:
            W.loc[d] = 0.0          # no tradable cross-section -> flat book this period
            continue
        r = row.rank()
        n = len(row)
        k = max(1, n // 3)
        longs = r.nlargest(k).index
        shorts = r.nsmallest(k).index
        w = pd.Series(0.0, index=sig.columns)
        w[longs] = 1.0 / len(longs)
        w[shorts] = -1.0 / len(shorts)
        W.loc[d] = w
    # hold weights between rebals
    return W.ffill().fillna(0.0)


def book_net(px: pd.DataFrame, lb: int, skip: int, rebal: int,
             target_vol: float = TARGET_VOL, cost_bps: float = COST_BPS) -> pd.Series:
    """Vol-targeted tercile L/S net return. Build raw L/S daily return from per-asset
    returns x weights, then scale by (target_vol / trailing realized book vol) using
    a CAUSAL (shift) vol so there is no look-ahead, lag 1d, charge turnover cost."""
    sig = xsec_mom(px, lb, skip)
    W = tercile_weights(sig, rebal)
    rets = px.pct_change()
    # raw gross L/S daily return from weights acting NEXT bar
    Wlag = W.shift(1)
    raw = (Wlag * rets).sum(axis=1)
    # causal vol-target scaler on the raw book
    rvol = raw.rolling(VOL_WIN).std() * np.sqrt(ANN)
    scale = (target_vol / rvol.replace(0, np.nan)).shift(1).clip(upper=4.0).fillna(0.0)
    gross = scale * raw
    # turnover cost: |Δ (scaled weight)| summed across assets, charged one-way
    scaled_W = W.mul(scale.reindex(W.index).fillna(0.0), axis=0)
    turnover = scaled_W.diff().abs().sum(axis=1).fillna(0.0)
    cost = (cost_bps / 1e4) * turnover.shift(1).fillna(0.0)
    return (gross - cost).rename("xsec_ls")


def dma_book(px: pd.DataFrame, win: int = 200, cost_bps: float = COST_BPS) -> pd.Series:
    """DUMB baseline: each-commodity long/flat 200dma (Faber), mean across, net."""
    ma = px.rolling(win).mean()
    alloc = (px > ma).astype(float).where(px.notna())
    legs = {c: backtest_core(px[c], alloc[c].fillna(0.0), cost_bps=cost_bps)["net"]
            for c in px.columns}
    return pd.DataFrame(legs).mean(axis=1)


def ew_long(px: pd.DataFrame) -> pd.Series:
    """DUMB baseline: equal-weight LONG commodity basket, daily-rebal buy&hold."""
    return px.pct_change().mean(axis=1)


# ---------------------------------------------------------------- metrics
def metrics(r: pd.Series) -> dict:
    r = r.dropna()
    if len(r) < 60:
        return {"n": len(r)}
    eq = (1.0 + r).cumprod()
    cagr = eq.iloc[-1] ** (ANN / len(r)) - 1.0
    return {"cagr": cagr * 100, "sharpe": _sharpe(r.to_numpy(), ANN),
            "maxdd": _maxdd(r.to_numpy()) * 100, "n": len(r)}


def fmt(label: str, m: dict, w: int = 32) -> str:
    if m.get("n", 0) < 60:
        return f"  {label:<{w}} (insufficient n={m.get('n', 0)})"
    return (f"  {label:<{w}} CAGR={m['cagr']:+6.2f}%  Sharpe={m['sharpe']:+5.2f}  "
            f"MaxDD={m['maxdd']:+7.1f}%  n={m['n']}")


# ---------------------------------------------------------------- forward rank-IC
def forward_ic_series(px: pd.DataFrame, lb: int, skip: int, h: int, rebal: int) -> list:
    """Per-rebal cross-sectional rank-IC: signal(t) vs forward h-day return.
    Forward target uses px.shift(-h) -> strictly out-of-sample (no look-ahead in signal)."""
    sig = xsec_mom(px, lb, skip)
    fwd = px.shift(-h) / px - 1.0
    ics = []
    for d in sig.index[::rebal]:
        ic = rank_ic(sig.loc[d], fwd.loc[d])
        if np.isfinite(ic):
            ics.append(ic)
    return ics


# ---------------------------------------------------------------- main
def main() -> None:
    out = []
    def p(s=""):
        print(s); out.append(s)

    px = collect().loc[:].copy()
    px.index = pd.to_datetime(px.index)
    # require >=10y per leg; drop anything too thin
    span_ok = {c: (px[c].dropna().index[-1] - px[c].dropna().index[0]).days / 365.25
               for c in px.columns if px[c].notna().sum() > 0}
    px = px[[c for c in px.columns if span_ok.get(c, 0) >= 10]]
    px_an = px.loc[START:]

    p("=" * 104)
    p("CROSS-SECTIONAL COMMODITY MOMENTUM (19-asset, deep) — Phase-0 (READ-ONLY)")
    p(f"  universe ({len(px.columns)}): {', '.join(px.columns)}")
    p(f"  full span {px.index.min().date()}..{px.index.max().date()}; analysis from {START}")
    p(f"  12-1m xsec rank, LONG top-tercile/SHORT bottom-tercile EW, vol-target {TARGET_VOL:.0%}, "
      f"rebal {REBAL}d, next-bar, {COST_BPS:.0f}bps one-way")
    for c in px.columns:
        s = px[c].dropna()
        p(f"    {c:<10} {s.index.min().date()}..{s.index.max().date()}  "
          f"({span_ok[c]:.1f}y, n={len(s)})")
    p("=" * 104)

    # ---- headline book + baselines ----------------------------------------
    book = book_net(px, LB, SKIP, REBAL).loc[START:]
    ew = ew_long(px).loc[START:]
    dma = dma_book(px).loc[START:]
    bm, em, dm = metrics(book), metrics(ew), metrics(dma)

    p("\n### HEADLINE L/S vs DUMB BASELINES (net of cost, from %s)" % START)
    p(fmt("xsec-mom L/S (12-1m, vt10)", bm))
    p(fmt("EW-long commodity B&H", em))
    p(fmt("each-commodity 200dma (long/flat)", dm))
    beats_ew = bm["sharpe"] > em["sharpe"]
    beats_dma = bm["sharpe"] > dm["sharpe"]
    p(f"  beats EW-long on Sharpe? {'YES' if beats_ew else 'NO'}  "
      f"({bm['sharpe']:+.3f} vs {em['sharpe']:+.3f}, margin {bm['sharpe']-em['sharpe']:+.3f})")
    p(f"  beats 200dma on Sharpe?  {'YES' if beats_dma else 'NO'}  "
      f"({bm['sharpe']:+.3f} vs {dm['sharpe']:+.3f})")

    # ---- forward rank-IC + FDR across the signal variants -----------------
    p("\n### FORWARD RANK-IC (xsec signal vs fwd %dd return) + BH-FDR across variants" % FWD_H)
    variants = {"mom_12_1": (LB, SKIP), "mom_12": (LB, 0), "mom_6_1": (126, SKIP), "mom_1": (21, 0)}
    pvals, ic_rows = {}, {}
    for nm, (lb, sk) in variants.items():
        ics = forward_ic_series(px_an, lb, sk, FWD_H, REBAL)
        summ = ic_summary(ics, periods_per_year=12)
        ic_rows[nm] = summ
        pv = summ.get("p_hac")
        if pv is not None:
            pvals[nm] = pv
        p(f"  {nm:<9} mean_IC={summ.get('mean_ic')}  IC-IR={summ.get('ic_ir')}  "
          f"t_HAC={summ.get('t_hac')}  p_HAC={summ.get('p_hac')}  hit={summ.get('hit')}  "
          f"n={summ.get('n')}")
    bh = benjamini_hochberg(pvals, alpha=0.10)
    p("  BH-FDR (q<=0.10):")
    for nm, r in bh.items():
        p(f"    {nm:<9} p={r['p']}  q={r['q']}  reject_null={r['reject']}")
    head_ic = ic_rows.get("mom_12_1", {})
    ic_fdr_pass = bool(bh.get("mom_12_1", {}).get("reject"))
    p(f"  -> headline mom_12_1 IC survives BH-FDR q<=0.10: {ic_fdr_pass}  "
      f"(mean_IC={head_ic.get('mean_ic')}, t_HAC={head_ic.get('t_hac')})")

    # ---- deflated Sharpe over the (lookback x rebal) grid ------------------
    n_grid = len(LB_GRID) * len(REBAL_GRID)
    p("\n### DEFLATED SHARPE — grid = %d lookbacks x %d rebals = %d trials"
      % (len(LB_GRID), len(REBAL_GRID), n_grid))
    grid_srs, best = [], None
    for (lb, sk) in LB_GRID:
        for rb in REBAL_GRID:
            b = book_net(px, lb, sk, rb).loc[START:]
            mm = metrics(b)
            if mm.get("n", 0) >= 60:
                sr = _sharpe(b.dropna().to_numpy(), ANN)
                grid_srs.append(sr)
                if best is None or mm["sharpe"] > best[1]["sharpe"]:
                    best = ((lb, sk, rb), mm, b)
    n_trials = len(grid_srs)
    sr_var = float(np.var(np.asarray(grid_srs) / np.sqrt(ANN), ddof=1)) if len(grid_srs) > 1 else None
    p(f"  grid annual-Sharpes: {[round(s,2) for s in grid_srs]}")
    p(f"  best-in-grid: lb={best[0][0]} skip={best[0][1]} rebal={best[0][2]}  "
      f"Sharpe={best[1]['sharpe']:+.2f}")
    dsr_head = None
    mom = ret_moments(book)
    if mom:
        sr_d, sk, ku, nT = mom
        d = deflated_sharpe(sr_d, sk, ku, nT, n_trials=n_trials, sr_variance=sr_var, trading_year=ANN)
        if d:
            dsr_head = d["dsr"]
            p(f"  HEADLINE 12-1m/vt10: SR(ann)={d['sr_annual']:+.2f}  "
              f"SR0(ann,haircut)={d['sr0_annual']:+.2f}  skew={d['skew']:+.2f}  "
              f"kurt={d['kurt']:.1f}  T={d['T']}")
            p(f"  DSR = {d['dsr']:.4f}  (n_trials={d['n_trials']})  -> {dsr_verdict(d['dsr'])}")
    dsr_best = None
    momb = ret_moments(best[2])
    if momb:
        sr_d, sk, ku, nT = momb
        db = deflated_sharpe(sr_d, sk, ku, nT, n_trials=n_trials, sr_variance=sr_var, trading_year=ANN)
        if db:
            dsr_best = db["dsr"]
            p(f"  BEST-IN-GRID DSR = {db['dsr']:.4f}  -> {dsr_verdict(db['dsr'])}")

    # ---- split-half same-sign ---------------------------------------------
    p("\n### SPLIT-HALF — same-sign Sharpe (and report vs EW each half)")
    n2 = len(book.dropna()) // 2
    split_date = book.dropna().index[n2]
    sh = {}
    for lab, sl in (("first", slice(None, split_date)), ("second", slice(split_date, None))):
        hb, he = book.loc[sl].dropna(), ew.loc[sl].dropna()
        sb = _sharpe(hb.to_numpy(), ANN); se = _sharpe(he.to_numpy(), ANN)
        sh[lab] = (sb, se)
        p(f"  {lab:<7} ({hb.index.min().date()}..{hb.index.max().date()}): "
          f"L/S Sharpe={sb:+.3f}  EW-long={se:+.3f}  beats_EW={'YES' if sb > se else 'NO'}")
    same_sign = (np.sign(sh["first"][0]) == np.sign(sh["second"][0])) and sh["first"][0] != 0
    both_pos = sh["first"][0] > 0 and sh["second"][0] > 0
    p(f"  -> same-sign = {same_sign}   both-halves-positive = {both_pos}")

    # ---- block-bootstrap CI on book Sharpe --------------------------------
    p("\n### BLOCK-BOOTSTRAP 95%% CI on L/S Sharpe (block=21, B=5000)")
    ci = block_bootstrap_ci(book, block=21, B=5000, ann=ANN)
    if ci:
        p(f"  Sharpe 95% CI {ci['sharpe_ci']}   MaxDD% 95% CI {ci['maxdd_ci_pct']}   "
          f"P(Sharpe>0)={ci['sharpe_gt0_prob']}")

    # ---- leave-one-crisis-out ---------------------------------------------
    p("\n### LEAVE-ONE-CRISIS-OUT — drop each crisis; L/S Sharpe stays >0 & beats EW")
    loco_ok = True
    for nm, a, b in CRISES:
        keep = ~((book.index >= a) & (book.index <= b))
        mb = metrics(book[keep]); me = metrics(ew.reindex(book.index)[keep])
        ok = mb["sharpe"] > 0 and mb["sharpe"] > me["sharpe"]
        loco_ok = loco_ok and ok
        p(f"  drop {nm:<18}: L/S Sharpe={mb['sharpe']:+.3f}  (EW {me['sharpe']:+.3f})  "
          f"-> {'holds' if ok else 'WEAK'}")
    p(f"  -> leave-one-crisis-out holds on ALL: {loco_ok}")

    # ---- crisis convexity --------------------------------------------------
    p("\n### CRISIS CONVEXITY — cumulative return through each window")
    p(f"  {'window':<20}{'L/S':>10}{'EW-long':>10}{'200dma':>10}")
    for nm, a, b in CRISES:
        def cum(r):
            w = r.loc[a:b].dropna()
            return (np.prod(1.0 + w.to_numpy()) - 1.0) * 100 if len(w) else float("nan")
        p(f"  {nm:<20}{cum(book):>9.1f}%{cum(ew):>9.1f}%{cum(dma):>9.1f}%")

    # ---- purged CV ---------------------------------------------------------
    p("\n### PURGED 5-FOLD CV (embargo=63d) — no fold should flip negative")
    fold_srs = []
    for k_, idx_ in purged_folds(book.index, k=5, embargo=63).items():
        s = book.reindex(idx_).dropna()
        sr = _sharpe(s.to_numpy(), ANN)
        fold_srs.append(sr)
        p(f"  {k_}: Sharpe={sr:+.2f}  (n={len(s)})")
    no_flip = all(s > 0 for s in fold_srs)
    p(f"  -> no fold flips negative: {no_flip}")

    # ---- honest-N ----------------------------------------------------------
    n_rebals = len(book.loc[START::REBAL]) if len(book) else 0
    p("\n### HONEST-N — a THIN cross-section; months autocorrelate")
    p(f"  raw daily rows: {bm['n']}   monthly rebals: ~{bm['n']//REBAL}   "
      f"span: ~{(book.index[-1]-book.index[0]).days/365.25:.1f}y")
    p(f"  cross-section width: {len(px.columns)} commodities (terciles ~{max(1,len(px.columns)//3)} long / "
      f"{max(1,len(px.columns)//3)} short) — THIN vs an equity factor (100s of names)")
    p("  Independent regimes ~ the 4 crisis clusters + a handful of multi-month commodity")
    p("  trends => honest-N ~6-10 regimes, NOT thousands of iid bets. A high in-sample IC-IR")
    p("  on 19 correlated assets is fragile; this is the small-N ceiling on commodity factors.")

    # ---- verdict -----------------------------------------------------------
    p("\n" + "=" * 104)
    gates = {
        "fwd rank-IC survives BH-FDR": (ic_fdr_pass,
            f"mom_12_1 q={bh.get('mom_12_1',{}).get('q')}, mean_IC={head_ic.get('mean_ic')}"),
        "DSR>=0.90 (headline)": (dsr_head is not None and dsr_head >= 0.90, f"DSR={dsr_head}"),
        "same-sign split-half": (same_sign, str({k: round(v[0],2) for k,v in sh.items()})),
        "leave-one-crisis-out": (loco_ok, "all hold" if loco_ok else "some WEAK"),
        "beats EW-long Sharpe": (beats_ew, f"{bm['sharpe']:+.3f} vs {em['sharpe']:+.3f}"),
        "beats 200dma Sharpe": (beats_dma, f"{bm['sharpe']:+.3f} vs {dm['sharpe']:+.3f}"),
        "no purged fold flips": (no_flip, str([round(s,2) for s in fold_srs])),
    }
    p("GATE SUMMARY:")
    for g, (ok, detail) in gates.items():
        p(f"  [{'PASS' if ok else 'FAIL'}] {g:<30} {detail}")
    scored = all(ok for ok, _ in gates.values())
    # confirmer = directionally real (IC positive-ish or beats one baseline) but fails the bar
    confirmer = (not scored) and (
        (head_ic.get("mean_ic") or 0) > 0 and (dsr_head is not None and dsr_head >= 0.50))
    tier = "SCORED" if scored else ("CONFIRMER" if confirmer else "DISPLAY/KILLED")
    p(f"\nVERDICT: {tier}")
    p(f"  scored requires ALL gates PASS. headline DSR={dsr_head} "
      f"({'>=' if (dsr_head or 0) >= 0.90 else '<'} 0.90); best-in-grid DSR={dsr_best}")
    p("=" * 104)

    rep = ROOT / "reports" / "commodity-xsec-mom-phase0.md"
    with open(rep, "w") as f:
        f.write("# Cross-sectional commodity momentum (19-asset, deep) — Phase-0\n\n```\n")
        f.write("\n".join(out))
        f.write("\n```\n")
    print(f"\n[written] {rep}")
    # tiny machine-readable footer for the orchestrator
    print(f"\nMACHINE: tier={tier} dsr_head={dsr_head} dsr_best={dsr_best} "
          f"ic_fdr={ic_fdr_pass} beats_ew={beats_ew} beats_dma={beats_dma} "
          f"same_sign={same_sign} loco={loco_ok} no_flip={no_flip} "
          f"sharpe={bm.get('sharpe')} n={bm.get('n')}")


if __name__ == "__main__":
    main()
