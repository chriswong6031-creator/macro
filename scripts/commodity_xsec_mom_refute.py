"""ADVERSARIAL REFUTATION probe for the commodity xsec-momentum KILLED tier.

We do NOT trust the validator's KILL blindly. Six attacks:
 (1) LOOKAHEAD       — re-derive IC with a strictly-shifted signal + non-overlapping fwd; recompute by hand.
 (2) DATA            — splice/jump detector on each leg (yfinance continuous front-month roll gaps).
 (3) MULTIPLE-TEST   — honest n_trials = lookbacks x rebal x (tercile vs quintile); recompute DSR for BEST.
 (4) BASELINE        — does ANY momentum variant beat EW-long AND 200dma net of 9bps? gross too.
 (5) HONEST-N        — effective independent regimes via IC autocorrelation + block count.
 (6) REGIME/DECAY    — split into supercycle(2002-2011)/post(2011-2026); IC + Sharpe per era.
PLUS: test the REVERSAL direction the validator declined, net of cost, to see if the "trap" is real.

READ-ONLY: prints + writes reports/commodity-xsec-mom-refute.md. Reuses cache.
"""
from __future__ import annotations
import sys, warnings
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from engine.validation import (rank_ic, ic_summary, deflated_sharpe, dsr_verdict,
                               ret_moments, _sharpe, _maxdd, benjamini_hochberg, newey_west_tstat)

# reuse the candidate's own machinery so we attack the SAME book
import importlib.util
spec = importlib.util.spec_from_file_location("cand", ROOT/"scripts"/"commodity_xsec_mom_phase0.py")
cand = importlib.util.module_from_spec(spec); spec.loader.exec_module(cand)

ANN = 252
out = []
def p(s=""):
    print(s); out.append(s)

px = cand.collect()
px.index = pd.to_datetime(px.index)
span_ok = {c:(px[c].dropna().index[-1]-px[c].dropna().index[0]).days/365.25 for c in px.columns if px[c].notna().sum()>0}
px = px[[c for c in px.columns if span_ok.get(c,0)>=10]]
START="2002-01-01"; px_an = px.loc[START:]

p("="*100); p("ADVERSARIAL REFUTATION — commodity xsec momentum"); p("="*100)

# ============================================================ (1) LOOKAHEAD
p("\n### (1) LOOKAHEAD — independent IC re-derivation (signal strictly past, fwd strictly future)")
# Manual, no reliance on cand: signal at month-end uses px through t only; fwd uses px.shift(-h).
def ic_manual(px, lb, skip, h, rebal, nonoverlap=False):
    sig = (px.shift(skip)/px.shift(lb)-1.0) if skip>0 else (px/px.shift(lb)-1.0)
    fwd = px.shift(-h)/px - 1.0
    dates = sig.index[::(h if nonoverlap else rebal)]
    ics=[]
    for d in dates:
        ic = rank_ic(sig.loc[d], fwd.loc[d])
        if np.isfinite(ic): ics.append(ic)
    return ics
for tag, no in [("overlapping 21d-rebal", False), ("NON-overlapping (rebal=h=21)", True)]:
    ics = ic_manual(px_an, 252, 21, 21, 21, nonoverlap=no)
    s = pd.Series(ics)
    nw = newey_west_tstat(s, lags=6)
    p(f"  mom_12_1 [{tag:<28}] mean_IC={s.mean():+.4f}  t_NW={nw['t']:+.2f}  p={nw['p']:.3f}  n={len(s)}")
# also confirm: SHUFFLE the forward target across assets -> IC must collapse to ~0 (null check)
rng = np.random.default_rng(7)
sig = px_an.shift(21)/px_an.shift(252)-1.0; fwd = px_an.shift(-21)/px_an-1.0
shuf_ics=[]
for d in sig.index[::21]:
    s_=sig.loc[d].dropna(); f_=fwd.loc[d].reindex(s_.index).dropna()
    s_=s_.reindex(f_.index)
    if len(f_)>=10:
        fperm = pd.Series(rng.permutation(f_.values), index=f_.index)
        ic=rank_ic(s_, fperm)
        if np.isfinite(ic): shuf_ics.append(ic)
p(f"  NULL check (shuffle fwd across names): mean_IC={np.mean(shuf_ics):+.4f} (should be ~0) n={len(shuf_ics)}")

# ============================================================ (2) DATA / splice
p("\n### (2) DATA — continuous-contract splice/roll-gap detector (daily log-ret outliers)")
lr = np.log(px/px.shift(1))
p(f"  {'leg':<10}{'maxAbsDayMove':>14}{'#|move|>25%':>12}{'#|move|>40%':>12}  (roll-gap / splice symptom)")
for c in px.columns:
    s = lr[c].dropna()
    p(f"  {c:<10}{np.exp(s.abs().max())-1:>13.1%}{int((s.abs()>0.223).sum()):>12d}{int((s.abs()>0.336).sum()):>12d}")
# survivorship: any leg dead before today?
p("  survivorship: last valid date per leg —")
stale = [(c, px[c].dropna().index[-1].date()) for c in px.columns if px[c].dropna().index[-1] < px.index.max()-pd.Timedelta(days=10)]
p(f"    delisted/stale legs (>10d behind last index date): {stale if stale else 'NONE (no survivorship gap)'}")

# ============================================================ (3) MULTIPLE-TESTING (expanded grid incl quintile)
p("\n### (3) MULTIPLE-TESTING — honest n_trials = lookbacks x rebal x (tercile|quintile)")
def book_q(px, lb, skip, rebal, frac):
    """tercile(frac=3)/quintile(frac=5) L/S, vol-targeted, net 9bps — generalize cand.book_net."""
    sig = cand.xsec_mom(px, lb, skip)
    idx=sig.index; W=pd.DataFrame(np.nan,index=idx,columns=sig.columns)
    for d in idx[::rebal]:
        row=sig.loc[d].dropna()
        if len(row)<frac*2: W.loc[d]=0.0; continue
        r=row.rank(); n=len(row); k=max(1,n//frac)
        longs=r.nlargest(k).index; shorts=r.nsmallest(k).index
        w=pd.Series(0.0,index=sig.columns); w[longs]=1.0/len(longs); w[shorts]=-1.0/len(shorts)
        W.loc[d]=w
    W=W.ffill().fillna(0.0); rets=px.pct_change()
    raw=(W.shift(1)*rets).sum(axis=1)
    rvol=raw.rolling(63).std()*np.sqrt(ANN)
    scale=(0.10/rvol.replace(0,np.nan)).shift(1).clip(upper=4.0).fillna(0.0)
    gross=scale*raw
    sw=W.mul(scale.reindex(W.index).fillna(0.0),axis=0)
    cost=(9.0/1e4)*sw.diff().abs().sum(axis=1).shift(1).fillna(0.0)
    return (gross-cost).rename("ls")
LBG=[(126,21),(252,21),(252,0),(21,0),(63,21)]; RBG=[5,10,21]; FRACS=[3,5]
srs=[]; best=None
for (lb,sk) in LBG:
    for rb in RBG:
        for fr in FRACS:
            b=book_q(px,lb,sk,rb,fr).loc[START:].dropna()
            if len(b)>=60:
                sr=_sharpe(b.to_numpy(),ANN); srs.append(sr)
                if best is None or sr>best[1]: best=((lb,sk,rb,fr),sr,b)
p(f"  honest n_trials = {len(LBG)}lb x {len(RBG)}rebal x {len(FRACS)}frac = {len(srs)} configs")
p(f"  grid Sharpes: {[round(s,2) for s in srs]}")
p(f"  BEST config lb={best[0][0]} skip={best[0][1]} rebal={best[0][2]} frac={best[0][3]} -> Sharpe={best[1]:+.3f}")
mom=ret_moments(best[2]); sr_var=float(np.var(np.asarray(srs)/np.sqrt(ANN),ddof=1))
if mom:
    sr_d,sk,ku,T=mom
    d=deflated_sharpe(sr_d,sk,ku,T,n_trials=len(srs),sr_variance=sr_var,trading_year=ANN)
    p(f"  BEST-of-{len(srs)} DSR={d['dsr']:.4f} (SR_ann={d['sr_annual']:+.2f}) -> {dsr_verdict(d['dsr'])}")
p(f"  ALL {len(srs)} grid Sharpes positive? {all(s>0 for s in srs)}   any>0? {any(s>0 for s in srs)}  max={max(srs):+.3f}")

# ============================================================ (4) BASELINE (gross + net, all variants)
p("\n### (4) BASELINE — does ANY momentum variant beat EW-long & 200dma? (gross AND net)")
ew=cand.ew_long(px).loc[START:]; dma=cand.dma_book(px).loc[START:]
ew_sr=_sharpe(ew.dropna().to_numpy(),ANN); dma_sr=_sharpe(dma.dropna().to_numpy(),ANN)
p(f"  baselines: EW-long Sharpe={ew_sr:+.3f}   200dma Sharpe={dma_sr:+.3f}")
for (lb,sk,tag) in [(252,21,"12-1m"),(126,21,"6-1m"),(252,0,"12m"),(63,21,"3-1m"),(21,0,"1m")]:
    b=book_q(px,lb,sk,21,3).loc[START:].dropna()
    # gross = recompute without cost
    sig=cand.xsec_mom(px,lb,sk); W=cand.tercile_weights(sig,21); raw=(W.shift(1)*px.pct_change()).sum(axis=1)
    rvol=raw.rolling(63).std()*np.sqrt(ANN); scale=(0.10/rvol.replace(0,np.nan)).shift(1).clip(upper=4.0).fillna(0.0)
    gross=(scale*raw).loc[START:].dropna()
    p(f"  mom {tag:<6}: NET Sharpe={_sharpe(b.to_numpy(),ANN):+.3f}  GROSS Sharpe={_sharpe(gross.to_numpy(),ANN):+.3f}"
      f"  beats both baselines net? {_sharpe(b.to_numpy(),ANN)>max(ew_sr,dma_sr)}")

# ============================================================ (5) HONEST-N
p("\n### (5) HONEST-N — effective independent regimes")
book = cand.book_net(px,252,21,21).loc[START:]
ics = cand.forward_ic_series(px_an,252,21,21,21)
s=pd.Series(ics)
# AR(1) of the IC series -> effective n
ac1 = s.autocorr(1)
n_raw=len(s); n_eff = n_raw*(1-ac1)/(1+ac1) if ac1 is not None and ac1< 1 else n_raw
p(f"  IC series: n={n_raw} monthly obs, AR(1)={ac1:+.3f}  -> effective indep IC obs ~ {n_eff:.0f}")
p(f"  cross-section width=19 -> terciles ~6 long/6 short; quintiles ~3/3 (very thin)")
p(f"  => even a TRUE |IC|~0.05 with n_eff~{n_eff:.0f} gives t~{0.05*np.sqrt(max(n_eff,1)):.2f} — at the noise floor")

# ============================================================ (6) REGIME / DECAY
p("\n### (6) REGIME/DECAY — supercycle 2002-2011 vs post-financialization 2011-2026")
for tag, sl in [("supercycle 2002-2011", slice("2002-01-01","2011-12-31")),
                ("post 2012-2026",       slice("2012-01-01",None))]:
    b=book.loc[sl].dropna()
    icz=cand.forward_ic_series(px.loc[sl],252,21,21,21); icz=pd.Series(icz)
    p(f"  {tag:<22}: L/S Sharpe={_sharpe(b.to_numpy(),ANN):+.3f}  mean_IC={icz.mean():+.4f}  n_ic={len(icz)}")
p("  (if momentum were real-but-decayed, supercycle IC>0 then erodes; here check the sign)")

# ============================================================ verdict
p("\n"+"="*100); p("REFUTATION VERDICT")
p("="*100)
rep=ROOT/"reports"/"commodity-xsec-mom-refute.md"
with open(rep,"w") as f:
    f.write("# Commodity xsec momentum — adversarial refutation\n\n```\n"+"\n".join(out)+"\n```\n")
print(f"\n[written] {rep}")
