"""Factor-exposure engine — Phase 0 honest validation (engine/factor_exposure.py).

This feature is MEASUREMENT, not prediction, so the gate is NOT predictive IC/FDR/DSR
— you don't backtest a thermometer. The honest questions are:

  1. COLLINEARITY — are the raw factors so correlated that a univariate beta table
     (the ChatGPT version) double-counts? Quantify it: VIF, top pairs, and the
     variance-inflation factor between the naive "sum of univariate exposures" and the
     orthogonal model's true factor variance. Confirm orthogonalization removes it.

  2. BETA STABILITY (the core gate) — does a beta estimated on the trailing window
     persist out-of-sample? At monthly rebalances, estimate betas on [t-W, t] (causal)
     and correlate them cross-sectionally with the realized betas on the next [t, t+H].
     A factor whose in-sample beta doesn't rank next-period exposure is noise.

  3. AGGREGATION DENOISING (the design justification) — the working assumption is
     "trust the portfolio aggregate, not a single stock's secondary beta." Form random
     K-name equal-weight books and show out-of-sample stability RISES with K, sharply
     for the noisy macro factors. If it doesn't, the whole portfolio-level read is moot.

  4. EXPLANATORY POWER — market-only vs full-model R², and how much the secondary
     factors add at the single-stock level (expected: little — hence point 3).

Run:
  .venv/bin/python -m scripts.factor_exposure_phase0
  .venv/bin/python -m scripts.factor_exposure_phase0 --win 252 --horizon 63

Writes reports/factor-exposure-phase0.md. No commit, no site build — pure harness.
"""
from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")   # rolling-beta on truncated history emits benign numpy warnings

from engine import factor_exposure as fe          # noqa: E402
from engine.equity_factors import _closes         # noqa: E402
from engine.validation import top_correlated_pairs, vif  # noqa: E402
from lib import config                             # noqa: E402

RNG = np.random.default_rng(7)


def _beta_series(betas: dict, key: str) -> pd.Series:
    """Pull one factor's beta across stocks as a Series (drops missing)."""
    return pd.Series({t: r[key] for t, r in betas.items()
                      if r.get(key) is not None}).astype(float)


def _spearman(a: pd.Series, b: pd.Series) -> float:
    j = pd.concat([a.rename("a"), b.rename("b")], axis=1).dropna()
    if len(j) < 10:
        return float("nan")
    return float(j["a"].rank().corr(j["b"].rank()))


def month_grid(index, warmup: int, horizon: int) -> list:
    out = []
    for me in pd.date_range(index.min(), index.max(), freq="ME"):
        d = index[index <= me]
        if not len(d):
            continue
        loc = index.get_loc(d[-1])
        if loc >= warmup and loc + horizon < len(index):
            out.append(d[-1])
    return out


# --------------------------------------------------------------------------- #
# 1. collinearity + double-count
# --------------------------------------------------------------------------- #
def collinearity(F: pd.DataFrame, closes: pd.DataFrame, win: int, minp: int,
                 max_abs: float) -> dict:
    raw_vif = vif(F)
    pairs = top_correlated_pairs(F, k=8, thresh=0.3)
    G = fe.orthogonalize_factors(F.tail(win))
    orth_vif = vif(G)

    # double-count: naive "sum of univariate exposures treating factors as independent"
    # variance vs the orthogonal model's true factor variance, per stock.
    rb = fe.raw_betas(closes, F, window=win, min_obs=minp, max_abs=max_abs)
    res = fe.stock_betas(closes, F, window=win, min_obs=minp, max_abs=max_abs)["betas"]
    keys = list(G.columns)
    raw_var = {k: float(F[k].tail(win).var()) for k in keys}
    orth_var = {k: float(G[k].var()) for k in keys}
    infl = []
    for t in res:
        if t not in rb:
            continue
        naive = sum((rb[t].get(k) or 0.0) ** 2 * raw_var[k] for k in keys)
        true = sum((res[t].get(k) or 0.0) ** 2 * orth_var[k] for k in keys)
        if true > 0:
            infl.append(naive / true)
    return {"raw_vif": raw_vif, "orth_vif": orth_vif, "pairs": pairs,
            "infl_median": float(np.median(infl)) if infl else None,
            "infl_p90": float(np.percentile(infl, 90)) if infl else None,
            "n_stocks": len(infl)}


# --------------------------------------------------------------------------- #
# 2+3. out-of-sample stability, per-stock and aggregated
# --------------------------------------------------------------------------- #
def stability(F: pd.DataFrame, closes: pd.DataFrame, *, win: int, horizon: int,
              minp: int, max_abs: float, basket_sizes: list, n_baskets: int) -> dict:
    idx = F.index.intersection(closes.index)
    closes = closes.reindex(idx)
    grid = month_grid(idx, warmup=win, horizon=horizon)
    keys = [k for k in fe.FACTOR_ORDER if k in F.columns]
    if len(grid) < 4:
        return {"error": f"grid too short ({len(grid)})", "rebalances": len(grid)}

    per_stock = {k: [] for k in keys}                     # cross-sectional persistence per date
    agg = {K: {k: [] for k in keys} for K in basket_sizes}
    fwd_minp = max(horizon // 2, 20)

    for d in grid:
        loc = idx.get_loc(d)
        in_sl = idx[max(0, loc - win):loc + 1]
        fw_sl = idx[loc:min(len(idx), loc + horizon + 1)]
        if len(fw_sl) < fwd_minp + 1:
            continue
        bin_ = fe.stock_betas(closes.loc[in_sl], F.loc[in_sl],
                              window=win, min_obs=minp, max_abs=max_abs)["betas"]
        bfw = fe.stock_betas(closes.loc[fw_sl], F.loc[fw_sl],
                             window=len(fw_sl), min_obs=fwd_minp, max_abs=max_abs)["betas"]
        if not bin_ or not bfw:
            continue
        for k in keys:
            si, sf = _beta_series(bin_, k), _beta_series(bfw, k)
            per_stock[k].append(_spearman(si, sf))
            common = si.index.intersection(sf.index)
            if len(common) < max(basket_sizes) + 5:
                continue
            si, sf = si[common], sf[common]
            for K in basket_sizes:
                ins, fws = [], []
                for _ in range(n_baskets):
                    pick = RNG.choice(common.to_numpy(), size=K, replace=False)
                    ins.append(float(si[pick].mean()))
                    fws.append(float(sf[pick].mean()))
                agg[K][k].append(_spearman(pd.Series(ins), pd.Series(fws)))

    def mean_n(xs):
        s = pd.Series(xs).dropna()
        return (round(float(s.mean()), 3), len(s)) if len(s) else (None, 0)

    ps = {k: dict(zip(("persist", "n"), mean_n(per_stock[k]))) for k in keys}
    ag = {K: {k: mean_n(agg[K][k])[0] for k in keys} for K in basket_sizes}
    return {"rebalances": len(grid), "span": f"{grid[0].date()}..{grid[-1].date()}",
            "horizon": horizon, "win": win, "per_stock": ps, "by_basket": ag,
            "basket_sizes": basket_sizes}


# --------------------------------------------------------------------------- #
# 4. explanatory power (market-only vs full model)
# --------------------------------------------------------------------------- #
def explanatory(F: pd.DataFrame, closes: pd.DataFrame, win: int, minp: int,
                max_abs: float) -> dict:
    """Nested R²: market-only → +style (growth, size) → full (+macro). Isolates how
    much the MACRO factors (rates/usd/oil/btc) actually add at the single-stock level."""
    style = [c for c in ("mkt", "growth", "size") if c in F.columns]

    def r2_of(cols):
        b = fe.stock_betas(closes, F[cols], window=win, min_obs=minp, max_abs=max_abs)["betas"]
        return pd.Series({t: r["r2"] for t, r in b.items() if r.get("r2") is not None})

    r2_mkt, r2_style, r2_full = r2_of(["mkt"]), r2_of(style), r2_of(list(F.columns))
    common = r2_mkt.index.intersection(r2_style.index).intersection(r2_full.index)
    macro_add = (r2_full[common] - r2_style[common]).dropna()
    style_add = (r2_style[common] - r2_mkt[common]).dropna()
    return {"r2_mkt_median": round(float(r2_mkt[common].median()), 3),
            "r2_style_median": round(float(r2_style[common].median()), 3),
            "r2_full_median": round(float(r2_full[common].median()), 3),
            "style_add_median": round(float(style_add.median()), 3),
            "macro_add_median": round(float(macro_add.median()), 3),
            "macro_add_p90": round(float(macro_add.quantile(0.9)), 3), "n": int(len(common))}


# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--win", type=int, default=252, help="estimation window (d)")
    ap.add_argument("--horizon", type=int, default=63, help="forward window for realized beta (d)")
    ap.add_argument("--min-obs", type=int, default=126)
    ap.add_argument("--max-abs", type=float, default=5.0)
    ap.add_argument("--n-baskets", type=int, default=200, help="random books per size per date")
    args = ap.parse_args()
    sizes = [1, 5, 10, 20, 40]

    F = fe.factor_frame()
    closes = _closes()
    if F.empty or closes.empty:
        print("missing factor or close data")
        return 1
    print(f"[factors] {list(F.columns)} · {len(F)} rows {F.index.min().date()}..{F.index.max().date()}")
    print(f"[stocks]  {closes.shape[1]} names · {len(closes)} rows")

    print("[1/4] collinearity + double-count …")
    col = collinearity(F, closes, args.win, args.min_obs, args.max_abs)
    print("[2-3/4] out-of-sample beta stability (per-stock + aggregated) …")
    stab = stability(F, closes, win=args.win, horizon=args.horizon, minp=args.min_obs,
                     max_abs=args.max_abs, basket_sizes=sizes, n_baskets=args.n_baskets)
    print("[4/4] explanatory power …")
    exp = explanatory(F, closes, args.win, args.min_obs, args.max_abs)

    report = render(F, col, stab, exp, args)
    out = config.ROOT / config.load()["storage"]["reports_dir"] / "factor-exposure-phase0.md"
    out.write_text(report)
    print(f"\n[report] {out}")
    return 0


def render(F, col, stab, exp, args) -> str:
    keys = [k for k in fe.FACTOR_ORDER if k in F.columns]
    lab = {f.key: f.label for f in fe.FACTORS}
    L = ["# Factor-exposure engine — Phase 0 validation", "",
         "*Generated by `scripts/factor_exposure_phase0.py`. This is a MEASUREMENT tool, "
         "not a predictive signal — the gate is collinearity control + out-of-sample beta "
         "STABILITY, not IC/FDR/DSR. Working assumption under test: trust the portfolio "
         "aggregate, not a single stock's secondary beta.*", ""]

    # 1. collinearity
    L += ["## 1. Collinearity — why a univariate beta table double-counts", "",
          "VIF per factor (>5 redundant, >10 severe) on the RAW factors vs after "
          "orthogonalization:", "",
          "| factor | raw VIF | orthogonalized VIF |", "|---|--:|--:|"]
    for k in keys:
        L.append(f"| {lab.get(k, k)} | {col['raw_vif'].get(k, '—')} | {col['orth_vif'].get(k, '—')} |")
    if col["pairs"]:
        L += ["", "Most-correlated raw factor pairs: "
              + ", ".join(f"{p['a']}–{p['b']} {p['corr']}" for p in col["pairs"]) + "."]
    if col["infl_median"] is not None:
        L += ["", f"**Double-count:** summing the univariate exposures (treating the factors as "
              f"independent — the naive table) overstates a stock's factor variance by a median "
              f"**{col['infl_median']:.2f}×** (p90 {col['infl_p90']:.2f}×) vs the orthogonal model, "
              f"across {col['n_stocks']} stocks. The orthogonal betas remove this."]

    # 2. per-stock stability
    L += ["", "## 2. Out-of-sample beta stability (single-stock)", ""]
    if stab.get("error"):
        L += [f"_skipped — {stab['error']}_", ""]
    else:
        L += [f"Span {stab['span']} · {stab['rebalances']} monthly rebalances · estimate on "
              f"{stab['win']}d, realize on next {stab['horizon']}d. Cross-sectional rank "
              f"correlation between in-sample and next-period beta (1 = perfectly persistent, "
              f"0 = noise):", "",
              "| factor | persistence | n |", "|---|--:|--:|"]
        for k in keys:
            r = stab["per_stock"][k]
            L.append(f"| {lab.get(k, k)} | {r['persist']} | {r['n']} |")

        # 3. aggregation denoising
        L += ["", "## 3. Aggregation denoising — does the portfolio aggregate firm up?", "",
              "Same persistence, but for random equal-weight books of K names (mean beta). "
              "If trustworthy only in aggregate, these rise with K:", "",
              "| factor | " + " | ".join(f"K={K}" for K in stab["basket_sizes"]) + " |",
              "|---|" + "--:|" * len(stab["basket_sizes"])]
        for k in keys:
            row = " | ".join(str(stab["by_basket"][K].get(k, "—")) for K in stab["basket_sizes"])
            L.append(f"| {lab.get(k, k)} | {row} |")

    # 4. explanatory
    L += ["", "## 4. Explanatory power (nested R²)", "",
          f"Median single-stock R² over {exp['n']} names: market-only **{exp['r2_mkt_median']}** "
          f"→ +style (growth, size) **{exp['r2_style_median']}** → +macro (rates/usd/oil/btc) "
          f"**{exp['r2_full_median']}**. Style adds a median **{exp['style_add_median']}**; the "
          f"MACRO factors add only **{exp['macro_add_median']}** (p90 {exp['macro_add_p90']}) — "
          f"tiny at the single-stock level, which is exactly why §3 (aggregation) carries the "
          f"macro read.", ""]

    L += ["---", "",
          "**How to read.** §1 justifies the orthogonal model over a univariate table. "
          "§2 says which single-stock betas are real (market/style ≫ macro). §3 is the "
          "load-bearing test: if macro-factor persistence climbs with book size, the "
          "PORTFOLIO exposure read is sound even where per-name betas are noisy — so ship "
          "the aggregate, show single-stock secondary betas as low-confidence context. If "
          "§3 stays flat, the macro factors are display-only at every level.", ""]
    return "\n".join(L)


if __name__ == "__main__":
    sys.exit(main())
