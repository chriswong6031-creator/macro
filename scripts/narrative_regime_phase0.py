"""Gate A — the decisive Phase-0 test for the Narrative-Dominance Index.

THE question that decides whether NDI can ever be a SCORED conditioner or stays a
display banner (memory narrative-quant-framework):

    Does the TEXT-uncertainty signal (EPU + GPR-threat) add forward-realized-
    volatility predictive content INCREMENTAL OVER VIX?

The replicated literature says text-uncertainty reads forward vol (so the RAW IC is
positive) but that VIX beats EPU at vol-forecasting — i.e. the INCREMENTAL content
over VIX is ~nil. The dashboard already scores the vol regime six ways, so a NDI vol
leg that is merely redundant with VIX must NOT become a scored leg. This harness
measures exactly that, on 36 years of daily data (1990-2026, far deeper than the
2023+ stock-cache window), and prints an honest GO / NO-GO.

Design (time-series, not cross-sectional):
  signal_t   = TU = mean of expanding-z(log EPU), expanding-z(log GPR_threat)   [PIT]
  target     = forward realized vol RVfwd(h) over t+1..t+h, h in {5,10,21,63}
  baseline   = VIX (VIXCLS) + trailing realized vol RVnow(21)
  raw IC     = Spearman(TU_t, RVfwd_h)            (expect strongly +, a sanity check)
  vix IC     = Spearman(VIX_t, RVfwd_h)            (expect strongly +)
  INCREMENTAL= Spearman(TU_t, residual of RVfwd_h ~ VIX + RVnow)   <-- the verdict
             + standardized OLS RVfwd_z ~ VIX_z + RVnow_z + TU_z : beta_TU
  significance via BLOCK BOOTSTRAP (overlapping forward windows autocorrelate, so
  naive t is inflated); FDR across horizons; sign-stability across split halves.

Run:  python scripts/narrative_regime_phase0.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import store  # noqa: E402

HORIZONS = [5, 10, 21, 63]
BLOCK = 63
B = 2000
SEED = 7
MINWIN = 252            # expanding-z burn-in


# --------------------------------------------------------------------------- #
def expanding_z(s: pd.Series, minp: int = MINWIN) -> pd.Series:
    """PIT standardization: (x - expanding mean) / expanding std, using only data
    available up to t. No look-ahead."""
    mu = s.expanding(min_periods=minp).mean()
    sd = s.expanding(min_periods=minp).std()
    return (s - mu) / sd


def load_aligned() -> pd.DataFrame:
    spx = store.read("yahoo", "_GSPC")["close"].astype(float)
    r = np.log(spx).diff().rename("r")
    vix = store.read("fred", "VIXCLS")["vix_close"].astype(float).rename("vix")
    epu = store.read("uncertainty", "epu_us")["epu"].astype(float)
    gprt = store.read("uncertainty", "gpr")["gpr_threat"].astype(float)

    # trading-day calendar = SPX
    idx = r.dropna().index
    # PIT text signal on the trading-day grid (last published value on/before t).
    # guard log against the odd non-positive index print (-> NaN, not -inf).
    def _safelog(s):
        return np.log(s.where(s > 0))
    tu = (0.5 * expanding_z(_safelog(epu.reindex(idx, method="ffill"))) +
          0.5 * expanding_z(_safelog(gprt.reindex(idx, method="ffill")))).rename("tu")
    vix = vix.reindex(idx, method="ffill")
    rvnow = (r.rolling(21).std() * np.sqrt(252)).rename("rvnow")

    df = pd.concat([r, vix, tu, rvnow], axis=1)
    for h in HORIZONS:
        # forward realized vol over t+1..t+h (strictly forward, no overlap with t)
        fwd = r.shift(-1).rolling(h).std().shift(-(h - 1)) * np.sqrt(252)
        df[f"rvfwd{h}"] = fwd
    return df


def resid_ols(y: pd.Series, X: pd.DataFrame) -> pd.Series:
    """Residual of y on [1, X...] via least squares (aligned, dropna)."""
    d = pd.concat([y.rename("y"), X], axis=1).dropna()
    A = np.column_stack([np.ones(len(d))] + [d[c].values for c in X.columns])
    beta, *_ = np.linalg.lstsq(A, d["y"].values, rcond=None)
    pred = A @ beta
    return pd.Series(d["y"].values - pred, index=d.index)


def std_ols_beta(y, Xcols: dict) -> dict:
    """Standardized OLS y ~ Xcols; return {name: beta} for each regressor."""
    d = pd.concat([pd.Series(y).rename("y")] + [pd.Series(v).rename(k) for k, v in Xcols.items()],
                  axis=1).dropna()
    def z(a): return (a - a.mean()) / a.std()
    yz = z(d["y"]).values
    names = list(Xcols)
    A = np.column_stack([z(d[n]).values for n in names])
    beta, *_ = np.linalg.lstsq(A, yz, rcond=None)
    return {n: float(b) for n, b in zip(names, beta)}


def boot_spearman_ci(sig: pd.Series, tgt: pd.Series, block=BLOCK, B=B, seed=SEED):
    """Block-bootstrap CI + two-sided p for a time-series Spearman IC."""
    d = pd.concat([sig.rename("s"), tgt.rename("t")], axis=1).dropna()
    if len(d) < block * 3:
        return None
    s, t = d["s"].values, d["t"].values
    n = len(s)
    point = spearmanr(s, t).statistic
    rng = np.random.default_rng(seed)
    nblocks = int(np.ceil(n / block))
    stats = np.empty(B)
    for b in range(B):
        starts = rng.integers(0, n - block + 1, size=nblocks)
        idx = np.concatenate([np.arange(st, st + block) for st in starts])[:n]
        stats[b] = spearmanr(s[idx], t[idx]).statistic
    lo, hi = np.percentile(stats, [5, 95])
    # two-sided bootstrap p: how often the resampled IC crosses 0 vs the point sign
    p = 2.0 * min((stats <= 0).mean(), (stats >= 0).mean()) if point != 0 else 1.0
    return {"ic": round(float(point), 4), "lo": round(float(lo), 4),
            "hi": round(float(hi), 4), "p": round(float(p), 4),
            "excl0": bool(lo > 0 or hi < 0)}


def main() -> None:
    df = load_aligned()
    # SPX returns reach back to 1927, but TU/VIX only start ~1990 — trim the frame to
    # the valid analysis window so the median split is an honest half of the DATA
    # (the pairwise-dropna ICs are unaffected; this only fixes the split-half index).
    start = df[["tu", "vix"]].dropna().index.min()
    df = df.loc[start:]
    print(f"\nNarrative-Dominance Index — Gate A (forward-vol IC, incremental over VIX)")
    print(f"sample: {df.dropna(subset=['tu','vix']).index.min().date()} -> "
          f"{df.index.max().date()}  ({len(df.dropna(subset=['tu','vix']))} obs)")
    corr_tv = df[["tu", "vix"]].dropna().corr(method="spearman").iloc[0, 1]
    print(f"TU vs VIX rank-corr (redundancy check): {corr_tv:+.3f}\n")

    half = df.index[len(df) // 2]
    inc_p: dict = {}
    rows = []
    for h in HORIZONS:
        y = df[f"rvfwd{h}"]
        raw = boot_spearman_ci(df["tu"], y)
        vixic = spearmanr(*df[["vix", f"rvfwd{h}"]].dropna().values.T).statistic
        resid = resid_ols(y, df[["vix", "rvnow"]])
        inc = boot_spearman_ci(df["tu"].reindex(resid.index), resid)
        beta = std_ols_beta(y, {"vix": df["vix"], "rvnow": df["rvnow"], "tu": df["tu"]})
        # split-half incremental sign stability
        rA = resid_ols(y.loc[:half], df.loc[:half, ["vix", "rvnow"]])
        rB = resid_ols(y.loc[half:], df.loc[half:, ["vix", "rvnow"]])
        icA = spearmanr(*pd.concat([df["tu"], rA], axis=1).dropna().values.T).statistic
        icB = spearmanr(*pd.concat([df["tu"], rB], axis=1).dropna().values.T).statistic
        inc_p[f"h{h}"] = inc["p"] if inc else None
        rows.append((h, raw, vixic, inc, beta["tu"], icA, icB))
        print(f"h={h:>2}d | raw IC(TU)={raw['ic']:+.3f} [{raw['lo']:+.3f},{raw['hi']:+.3f}]"
              f" | IC(VIX)={vixic:+.3f}"
              f" | INCREMENTAL IC(TU|VIX,RVnow)={inc['ic']:+.3f} [{inc['lo']:+.3f},{inc['hi']:+.3f}]"
              f" excl0={inc['excl0']} | beta_TU={beta['tu']:+.3f}"
              f" | half-split inc IC: {icA:+.3f}/{icB:+.3f}")

    from engine.validation import benjamini_hochberg
    fdr = benjamini_hochberg({k: v for k, v in inc_p.items() if v is not None}, alpha=0.10)
    print(f"\nBH-FDR on INCREMENTAL p-values (q<=0.10):")
    for k, v in sorted(fdr.items()):
        print(f"  {k}: p={v['p']} q={v['q']} reject={v['reject']}")

    # verdict
    survivors = []
    for (h, raw, vixic, inc, btu, icA, icB) in rows:
        signstable = (icA > 0) == (icB > 0) and abs(icA) > 1e-3 and abs(icB) > 1e-3
        fdrok = fdr.get(f"h{h}", {}).get("reject", False)
        incpos = inc["excl0"] and inc["ic"] > 0
        if incpos and fdrok and signstable and icA > 0:
            survivors.append(h)
    print("\n" + "=" * 72)
    if survivors:
        print(f"GATE A: PASS at horizons {survivors} — text-uncertainty adds POSITIVE "
              f"forward-vol content incremental over VIX (FDR-surviving, sign-stable).")
        print("  -> NDI vol leg is a CANDIDATE scored conditioner; proceed to Gate B.")
    else:
        print("GATE A: FAIL (as the literature predicts) — text-uncertainty adds NO "
              "robust forward-vol content beyond VIX (no horizon clears incremental "
              "IC>0 with FDR + sign-stable halves).")
        print("  -> NDI is REDUNDANT with VIX for vol; ship DISPLAY-ONLY, keep "
              "gate_multiplier pinned 1.0. Do NOT build the P2 scored gate.")
    print("=" * 72)


if __name__ == "__main__":
    main()
