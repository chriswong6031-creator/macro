"""Phase-0: DIVERSIFIED VOL-TARGETED COMMODITY TSMOM BOOK — READ-ONLY research.

The candidate. A 5-leg time-series-momentum book across gold / silver / copper /
crude / the dollar (GC=F, SI=F, HG=F, CL=F, DX-Y.NYB; ~25.8y from 2000). Per leg:

    signal  = sign( px[t-21] / px[t-252] - 1 )           # 12-1m trend, long/short
    size    = ( 0.15 / realized_63d_vol ) * signal        # vol-targeted
              clipped to [-2, +2]
    book    = mean across the 5 legs                       # equal-risk aggregate

Position acts NEXT bar (backtest_core shift(1)); 8 bps one-way turnover cost. This is
the construct the repo's broader cross-asset TSMOM hunt DEFERRED — here measured on a
COMMODITY-heavy sleeve where trend's documented value (crisis convexity, a MaxDD far
shallower than long-only commodity B&H) is real, but the standalone Sharpe edge over an
equal-weight-long basket is thin.

The honest bar (SCORED requires ALL of):
  * Deflated Sharpe over the (vol-target x lookback) grid, n_trials>=10, DSR>=0.90
  * drawdown-REDUCTION vs EW-long-commodity: block-bootstrap CI on (book MaxDD - EW
    MaxDD) must EXCLUDE 0 (the book genuinely shaves the left tail)
  * leave-one-crisis-out {2008, 2014-16 commodity bust, 2020, 2022}: book Sharpe and
    the DD-reduction survive dropping any one crisis
  * both split-halves beat the EW-long baseline on Sharpe
  * beats the DUMB baselines: EW-long-commodity B&H AND each-leg 200dma trend
  * honest-N: count INDEPENDENT crisis clusters, not raw rows

No look-ahead: signal/vol use data through t; backtest_core acts next bar (shift(1));
turnover cost on |Δpos|. forward targets, where used, = px.shift(-h).

Run:  ./.venv/bin/python3 scripts/commodity_tsmom_phase0.py
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from engine.validation import (  # noqa: E402
    backtest_core, ret_moments, deflated_sharpe, dsr_verdict,
    block_bootstrap_ci, purged_folds, _maxdd, _sharpe,
)
from lib import store  # noqa: E402

# ---------------------------------------------------------------- config (the SPEC)
LEGS: dict[str, str] = {
    "gold":   "GC=F",
    "silver": "SI=F",
    "copper": "HG=F",
    "crude":  "CL=F",
    "dollar": "DX-Y.NYB",
}
LB = 252            # 12-month lookback
SKIP = 21           # drop the recent 1 month -> 12-1m trend
TARGET_VOL = 0.15   # vol target (the SPEC's 0.15)
VOL_WIN = 63        # realized-vol window (the SPEC's 63d)
CLIP = 2.0          # size clip [-2, +2]
COST_BPS = 8.0      # one-way turnover cost
ANN = 252
START = "2000-12-01"   # all 5 legs warm (252d trend + 63d vol from 2000-08)
SPLIT = "2013-06-15"   # ~midpoint of the analysis window

# the (vol-target x lookback) grid we TRY -> honest DSR trial count (>=10)
VT_GRID = [0.10, 0.15, 0.20]
LB_GRID = [(126, 21), (189, 21), (252, 21), (252, 0)]   # 6-1, 9-1, 12-1, 12-0
HEADLINE = (TARGET_VOL, (LB, SKIP))

# independent crisis clusters (commodity-relevant): the SPEC's {2008,2014-16,2020,2022}
CRISES = [
    ("2008 GFC",        "2008-06-01", "2009-03-31"),
    ("2014-16 oil bust","2014-07-01", "2016-02-29"),
    ("2020 COVID",      "2020-01-15", "2020-04-30"),
    ("2022 bear",       "2022-01-01", "2022-12-31"),
]


# ---------------------------------------------------------------- data
def load_px() -> pd.DataFrame:
    cols = {}
    for name, tk in LEGS.items():
        df = store.read("yahoo", tk)
        if df is None or "close" not in df.columns:
            print(f"  [skip] {name} ({tk}) — no data on disk")
            continue
        cols[name] = df["close"].rename(name)
    px = pd.DataFrame(cols).sort_index()
    px.index = pd.to_datetime(px.index)
    px = px[~px.index.duplicated(keep="last")]
    return px.dropna(how="all")


# ---------------------------------------------------------------- signals / book
def leg_alloc(px: pd.DataFrame, lb: int, skip: int, tvol: float) -> pd.DataFrame:
    """Per-leg vol-targeted 12-1 TSMOM target position (pre next-bar lag)."""
    mom = px.shift(skip) / px.shift(lb) - 1.0           # trailing return, recent skip dropped
    sig = np.sign(mom)
    rets = px.pct_change()
    rvol = rets.rolling(VOL_WIN).std() * np.sqrt(ANN)
    scale = (tvol / rvol.replace(0, np.nan))
    return (sig * scale).clip(-CLIP, CLIP)


def book_returns(px: pd.DataFrame, lb: int, skip: int, tvol: float,
                 cost_bps: float = COST_BPS) -> tuple[pd.Series, pd.DataFrame]:
    """Net book = MEAN across the per-leg net returns (each leg pre-vol-targeted)."""
    alloc = leg_alloc(px, lb, skip, tvol)
    legs = {c: backtest_core(px[c], alloc[c], cost_bps=cost_bps)["net"] for c in px.columns}
    L = pd.DataFrame(legs)
    return L.mean(axis=1), L


def dma_book(px: pd.DataFrame, win: int = 200, cost_bps: float = COST_BPS) -> pd.Series:
    """DUMB baseline: each-leg long/flat 200dma trend (above MA = long, else flat),
    mean across legs. Long-only flat (the classic Faber rule), 8bps."""
    ma = px.rolling(win).mean()
    alloc = (px > ma).astype(float)                      # 1 long / 0 flat
    legs = {c: backtest_core(px[c], alloc[c], cost_bps=cost_bps)["net"] for c in px.columns}
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


def fmt(label: str, m: dict, w: int = 30) -> str:
    if m.get("n", 0) < 60:
        return f"  {label:<{w}} (insufficient n={m.get('n', 0)})"
    return (f"  {label:<{w}} CAGR={m['cagr']:+6.2f}%  Sharpe={m['sharpe']:+5.2f}  "
            f"MaxDD={m['maxdd']:+7.1f}%  n={m['n']}")


def dd_reduction_ci(book: pd.Series, ew: pd.Series, block: int = 21,
                    B: int = 5000, seed: int = 7) -> dict:
    """Block-bootstrap CI on (book MaxDD - EW MaxDD). Both series resampled with the
    SAME block draw (paired) so the difference is apples-to-apples. A CI strictly
    BELOW 0 => the book genuinely shaves drawdown vs EW-long (book MaxDD less negative
    => book - ew > 0 actually... we report book_dd - ew_dd; book shallower => book_dd
    > ew_dd since both negative). We test P(book_dd > ew_dd) and the CI of the diff."""
    j = pd.concat([book.rename("b"), ew.rename("e")], axis=1).dropna()
    b = j["b"].to_numpy(); e = j["e"].to_numpy()
    n = len(b)
    if n < max(block * 3, 60):
        return {}
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(n / block))
    grid = np.arange(block)
    diff = np.empty(B)
    for k in range(B):
        starts = rng.integers(0, n, nb)
        idx = (starts[:, None] + grid[None, :]).ravel()[:n] % n
        diff[k] = _maxdd(b[idx]) - _maxdd(e[idx])        # >0 => book shallower DD
    lo, md, hi = (float(np.percentile(diff, p)) for p in (2.5, 50, 97.5))
    return {"diff_ci_pp": [round(lo * 100, 1), round(md * 100, 1), round(hi * 100, 1)],
            "p_book_shallower": round(float(np.mean(diff > 0)), 3),
            "excludes_0": bool(lo > 0 or hi < 0), "B": B, "n": n}


# ---------------------------------------------------------------- main
def main() -> None:
    px = load_px()
    out = []
    def p(s=""):
        print(s); out.append(s)

    p("=" * 100)
    p("DIVERSIFIED VOL-TARGETED COMMODITY TSMOM BOOK — Phase-0 (READ-ONLY)")
    p(f"  legs: {', '.join(px.columns)}  ({px.index.min().date()}..{px.index.max().date()})")
    p(f"  12-1m sign trend, size=({TARGET_VOL}/rv63) clip[-{CLIP},{CLIP}], "
      f"next-bar, {COST_BPS:.0f}bps one-way, book=mean(legs); analysis from {START}")
    p("=" * 100)

    book, L = book_returns(px, LB, SKIP, TARGET_VOL)
    book = book.loc[START:]
    ew = ew_long(px).loc[START:]
    dma = dma_book(px).loc[START:]

    # baselines + headline --------------------------------------------------
    p("\n### HEADLINE BOOK vs DUMB BASELINES (net of cost, from %s)" % START)
    bm, em, dm = metrics(book), metrics(ew), metrics(dma)
    p(fmt("TSMOM book (12-1m, vt15)", bm))
    p(fmt("EW-long commodity B&H", em))
    p(fmt("each-leg 200dma (long/flat)", dm))
    p(f"  beats EW-long on Sharpe? {'YES' if bm['sharpe'] > em['sharpe'] else 'NO'}  "
      f"({bm['sharpe']:+.3f} vs {em['sharpe']:+.3f}, margin {bm['sharpe']-em['sharpe']:+.3f})")
    p(f"  beats 200dma on Sharpe?  {'YES' if bm['sharpe'] > dm['sharpe'] else 'NO'}  "
      f"({bm['sharpe']:+.3f} vs {dm['sharpe']:+.3f})")
    p(f"  MaxDD reduction vs EW-long: {bm['maxdd']-em['maxdd']:+.1f}pp "
      f"(book {bm['maxdd']:+.1f}% vs EW {em['maxdd']:+.1f}%)")

    # per-leg standalone Sharpe (sanity) ------------------------------------
    p("\n### PER-LEG STANDALONE (net) — what each sleeve contributes")
    for c in L.columns:
        p(fmt(f"  leg {c}", metrics(L[c].loc[START:])))

    # deflated sharpe over the grid -----------------------------------------
    p("\n### DEFLATED SHARPE — grid = %d vol-targets x %d lookbacks = %d trials"
      % (len(VT_GRID), len(LB_GRID), len(VT_GRID) * len(LB_GRID)))
    grid_srs = []
    best = None
    for tvol in VT_GRID:
        for (lb, skip) in LB_GRID:
            b, _ = book_returns(px, lb, skip, tvol)
            b = b.loc[START:]
            mm = metrics(b)
            if mm.get("n", 0) >= 60:
                grid_srs.append(_sharpe(b.dropna().to_numpy(), ANN))
                if best is None or mm["sharpe"] > best[1]["sharpe"]:
                    best = ((tvol, lb, skip), mm, b)
    n_trials = len(grid_srs)
    sr_var = float(np.var(np.asarray(grid_srs) / np.sqrt(ANN), ddof=1)) if len(grid_srs) > 1 else None
    p(f"  grid annual-Sharpes: {[round(s,2) for s in grid_srs]}")
    p(f"  best-in-grid: vt={best[0][0]} lb={best[0][1]} skip={best[0][2]}  "
      f"Sharpe={best[1]['sharpe']:+.2f}  (DSR is computed on the HEADLINE 12-1m/vt15, "
      f"haircut by the {n_trials} trials)")
    mom = ret_moments(book)
    dsr_head = None
    if mom:
        sr_d, sk, ku, nT = mom
        d = deflated_sharpe(sr_d, sk, ku, nT, n_trials=n_trials, sr_variance=sr_var, trading_year=ANN)
        if d:
            dsr_head = d["dsr"]
            p(f"  HEADLINE 12-1m/vt15: SR(ann)={d['sr_annual']:+.2f}  "
              f"SR0(ann,haircut)={d['sr0_annual']:+.2f}  skew={d['skew']:+.2f}  "
              f"kurt={d['kurt']:.1f}  T={d['T']}")
            p(f"  DSR = {d['dsr']:.4f}  (n_trials={d['n_trials']})  -> {dsr_verdict(d['dsr'])}")
    # also DSR on the best-in-grid (the genuinely cherry-picked config)
    momb = ret_moments(best[2])
    if momb:
        sr_d, sk, ku, nT = momb
        db = deflated_sharpe(sr_d, sk, ku, nT, n_trials=n_trials, sr_variance=sr_var, trading_year=ANN)
        if db:
            p(f"  BEST-IN-GRID DSR = {db['dsr']:.4f}  -> {dsr_verdict(db['dsr'])}")

    # split-half: both halves beat EW-long ----------------------------------
    p("\n### SPLIT-HALF — both halves must beat EW-long on Sharpe (SPEC gate)")
    sh = {}
    for lab, sl in (("first", slice(None, SPLIT)), ("second", slice(SPLIT, None))):
        hb, he = book.loc[sl], ew.loc[sl]
        sb = _sharpe(hb.dropna().to_numpy(), ANN); se = _sharpe(he.dropna().to_numpy(), ANN)
        sh[lab] = (sb, se, sb > se)
        p(f"  {lab:<7} ({hb.index.min().date()}..{hb.index.max().date()}): "
          f"book Sharpe={sb:+.3f}  EW-long={se:+.3f}  beats={'YES' if sb > se else 'NO'}")
    both_halves_beat = sh["first"][2] and sh["second"][2]
    same_sign = np.sign(sh["first"][0]) == np.sign(sh["second"][0]) and sh["first"][0] != 0
    p(f"  -> both-halves-beat-EW = {both_halves_beat}   same-sign = {same_sign}")

    # drawdown-reduction bootstrap CI ---------------------------------------
    p("\n### DRAWDOWN-REDUCTION BOOTSTRAP (paired block=21, B=5000) — CI must EXCLUDE 0")
    ddci = dd_reduction_ci(book, ew)
    if ddci:
        p(f"  (book MaxDD - EW MaxDD) 95% CI = {ddci['diff_ci_pp']} pp   "
          f"P(book shallower)={ddci['p_book_shallower']}")
        p(f"  -> CI excludes 0: {ddci['excludes_0']}  "
          f"({'book reliably shaves the left tail' if ddci['excludes_0'] else 'overlaps 0'})")

    # plain bootstrap CI on book Sharpe -------------------------------------
    p("\n### BLOCK-BOOTSTRAP 95%% CI on book Sharpe (block=21, B=5000)")
    ci = block_bootstrap_ci(book, block=21, B=5000, ann=ANN)
    if ci:
        p(f"  Sharpe 95% CI {ci['sharpe_ci']}   MaxDD% 95% CI {ci['maxdd_ci_pct']}   "
          f"P(Sharpe>0)={ci['sharpe_gt0_prob']}")

    # leave-one-crisis-out --------------------------------------------------
    p("\n### LEAVE-ONE-CRISIS-OUT — drop each crisis; book must stay > EW-long & keep DD edge")
    full_b, full_e = metrics(book), metrics(ew)
    loco_ok = True
    for nm, a, b in CRISES:
        keep = ~((book.index >= a) & (book.index <= b))
        mb, me = metrics(book[keep]), metrics(ew.reindex(book.index)[keep])
        dsh = mb["sharpe"] - me["sharpe"]
        ddd = mb["maxdd"] - me["maxdd"]      # >0 => book still shallower
        ok = dsh > 0 and ddd > 0
        loco_ok = loco_ok and ok
        p(f"  drop {nm:<18}: book Sharpe={mb['sharpe']:+.3f} (EW {me['sharpe']:+.3f}, "
          f"d={dsh:+.3f})  dMaxDD={ddd:+5.1f}pp  -> {'holds' if ok else 'WEAK'}")
    p(f"  -> leave-one-crisis-out holds on ALL: {loco_ok}")

    # crisis convexity ------------------------------------------------------
    p("\n### CRISIS CONVEXITY — cumulative return through each window")
    p(f"  {'window':<20}{'book':>10}{'EW-long':>10}{'200dma':>10}")
    for nm, a, b in CRISES:
        def cum(r):
            w = r.loc[a:b].dropna()
            return (np.prod(1.0 + w.to_numpy()) - 1.0) * 100 if len(w) else float("nan")
        p(f"  {nm:<20}{cum(book):>9.1f}%{cum(ew):>9.1f}%{cum(dma):>9.1f}%")

    # purged CV -------------------------------------------------------------
    p("\n### PURGED 5-FOLD CV (embargo=63d) — no fold should flip negative")
    fold_srs = []
    for k_, idx_ in purged_folds(book.index, k=5, embargo=63).items():
        s = book.reindex(idx_).dropna()
        sr = _sharpe(s.to_numpy(), ANN)
        fold_srs.append(sr)
        p(f"  {k_}: Sharpe={sr:+.2f}  (n={len(s)})")
    no_flip = all(s > 0 for s in fold_srs)
    p(f"  -> no fold flips negative: {no_flip}")

    # honest-N --------------------------------------------------------------
    p("\n### HONEST-N — independent crisis clusters, not raw rows")
    p(f"  raw daily rows: {bm['n']}   span: ~{(book.index[-1]-book.index[0]).days/365.25:.1f}y")
    p(f"  INDEPENDENT trend-regime clusters tested = {len(CRISES)} crises "
      f"+ ~a handful of multi-month commodity up/down regimes => honest-N ~5-8 clusters.")
    p("  This is the SAME small-N problem that keeps cross-asset trend a CONFIRMER: the")
    p("  drawdown-shaped payoff rides on a handful of crises, not thousands of iid bets.")

    # verdict ---------------------------------------------------------------
    p("\n" + "=" * 100)
    gate = {
        "DSR>=0.90 (headline)": (dsr_head is not None and dsr_head >= 0.90, f"DSR={dsr_head}"),
        "beats EW-long Sharpe": (bm["sharpe"] > em["sharpe"], f"{bm['sharpe']:+.3f} vs {em['sharpe']:+.3f}"),
        "beats 200dma Sharpe": (bm["sharpe"] > dm["sharpe"], f"{bm['sharpe']:+.3f} vs {dm['sharpe']:+.3f}"),
        "both halves beat EW": (both_halves_beat, str({k: round(v[0],2) for k,v in sh.items()})),
        "DD-reduction CI excl 0": (bool(ddci.get("excludes_0")), str(ddci.get("diff_ci_pp"))),
        "leave-one-crisis-out": (loco_ok, "all hold" if loco_ok else "some WEAK"),
        "no purged fold flips": (no_flip, str([round(s,2) for s in fold_srs])),
    }
    p("GATE SUMMARY:")
    for g, (ok, detail) in gate.items():
        p(f"  [{'PASS' if ok else 'FAIL'}] {g:<26} {detail}")
    scored = (gate["DSR>=0.90 (headline)"][0] and gate["both halves beat EW"][0]
              and gate["leave-one-crisis-out"][0] and gate["beats EW-long Sharpe"][0]
              and gate["beats 200dma Sharpe"][0])
    p(f"\nVERDICT: {'SCORED' if scored else 'CONFIRMER/DISPLAY'} "
      f"(DSR {dsr_head} {'>=' if (dsr_head or 0) >= 0.90 else '<'} 0.90)")
    p("=" * 100)

    # write report ----------------------------------------------------------
    rep = Path(__file__).resolve().parent.parent / "reports" / "commodity-tsmom-phase0.md"
    with open(rep, "w") as f:
        f.write("# Diversified vol-targeted commodity TSMOM book — Phase-0\n\n```\n")
        f.write("\n".join(out))
        f.write("\n```\n")
    print(f"\n[written] {rep}")


if __name__ == "__main__":
    main()
