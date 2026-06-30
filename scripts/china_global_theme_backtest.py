"""Does GLOBAL AI-narrative momentum predict next-week returns of the mapped CN
AI-supply baskets? (The owner's "follow global narrative momentum" question, and the
one leg the deep-research design CLAIMED but never actually ran.)

Signal  : EW trailing 4-week log-momentum of the global semis narrative (SMH+SOXX+TSM).
Target  : next-week (t+1) EW return of each THS AI-supply basket (cpo/pcb/storage_chip/
          adv_pkg/liquid_cool/aidc/ai), built from data/baskets_china_ths/membership.json
          x data/china_search/closes.parquet.
Controls: SPY 4w momentum (generic global risk-on) + EW-A-share-universe 4w momentum
          (CN-own). The semis leg must STAY significant with these in (horse race).
Placebo : ths_baijiu / ths_gold / ths_innovative_rx — semis momentum should NOT predict these.
Splits  : full / pre-2024 / 2024+  — the KEY test: does it survive OUTSIDE the 2024 AI run,
          or is the whole "theme" just "AI went up in 2024"?

Leak-free: US week-t is fully closed before CN week t+1; weekly W-FRI; non-overlapping
target. Newey-West HAC t-stats (lags=4) computed by hand (no statsmodels).
Survivorship caveat: THS membership is a single 2026 snapshot back-applied — composition
is hindsight-curated; this tests TIME-SERIES predictability by an EXTERNAL signal, which
survivorship in composition affects far less than a cross-sectional selection claim.

Run: .venv/bin/python -m scripts.china_global_theme_backtest
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
from scipy import stats

from lib import config

THS = "data/baskets_china_ths/membership.json"
CN = "data/china_search/closes.parquet"
AI = ["ths_ai", "ths_cpo", "ths_pcb", "ths_storage_chip", "ths_adv_pkg", "ths_liquid_cool", "ths_aidc"]
PLACEBO = ["ths_baijiu", "ths_gold", "ths_innovative_rx"]
SEMIS = ["SMH", "SOXX", "TSM"]
MOM_WK = 4                                 # trailing momentum window (weeks)


def nw_ols(y, cols, names, lags=4):
    """OLS y ~ const + cols, Newey-West HAC t per regressor. Returns {name:(beta,t,p), _n}."""
    y = np.asarray(y, float)
    M = np.column_stack([np.asarray(c, float) for c in cols])
    mask = ~np.isnan(y)
    for j in range(M.shape[1]):
        mask &= ~np.isnan(M[:, j])
    y, M = y[mask], M[mask]
    n = len(y)
    if n < 25:
        return {"_n": n}
    X = np.column_stack([np.ones(n), M])
    k = X.shape[1]
    XtX_inv = np.linalg.inv(X.T @ X)
    beta = XtX_inv @ X.T @ y
    u = X * (y - X @ beta)[:, None]
    S = u.T @ u
    for l in range(1, lags + 1):
        w = 1 - l / (lags + 1)
        G = u[l:].T @ u[:-l]
        S += w * (G + G.T)
    se = np.sqrt(np.diag(XtX_inv @ S @ XtX_inv))
    out = {"_n": n}
    for i, nm in enumerate(names):
        b, s = beta[i + 1], se[i + 1]
        t = b / s if s > 0 else np.nan
        p = 2 * (1 - stats.t.cdf(abs(t), n - k)) if np.isfinite(t) else np.nan
        out[nm] = (round(float(b), 4), round(float(t), 2), round(float(p), 4))
    return out


def ew_level(closes: pd.DataFrame, tickers: list) -> pd.Series:
    cols = [t for t in tickers if t in closes.columns]
    if len(cols) < 3:
        return pd.Series(dtype=float)
    ew = closes[cols].pct_change(fill_method=None).mean(axis=1, skipna=True)
    return (1 + ew.fillna(0)).cumprod()


def weekly(level: pd.Series) -> pd.Series:
    return level.resample("W-FRI").last()


def main() -> int:
    root = config.ROOT
    closes = pd.read_parquet(root / CN).sort_index()
    closes = closes.loc[:, ~closes.columns.duplicated()]
    baskets = json.load(open(root / THS))["baskets"]

    def members(bid):
        v = baskets[bid]
        rows = v if isinstance(v, list) else (v.get("members") or v.get("tickers") or [])
        return [(r["ticker"] if isinstance(r, dict) else r) for r in rows]

    # weekly returns per basket
    bret = {}
    for bid in AI + PLACEBO:
        lv = ew_level(closes, members(bid))
        if not lv.empty:
            bret[bid] = weekly(lv).pct_change()

    # global semis narrative + controls -> weekly trailing MOM_WK-week momentum (signal at week t)
    yhz = root / "data" / "yahoo"
    semis_lv = pd.concat([pd.read_parquet(yhz / f"{s}.parquet")["close"] for s in SEMIS], axis=1)
    semis_w = weekly((1 + semis_lv.pct_change().mean(axis=1)).cumprod())
    spy_w = weekly(pd.read_parquet(yhz / "SPY.parquet")["close"])
    cnmkt_w = weekly(ew_level(closes, list(closes.columns)))     # EW A-share universe (CN-own)

    semis_mom = np.log(semis_w / semis_w.shift(MOM_WK))
    spy_mom = np.log(spy_w / spy_w.shift(MOM_WK))
    cn_mom = np.log(cnmkt_w / cnmkt_w.shift(MOM_WK))

    eras = {"full": (None, None), "pre-2024": (None, "2023-12-31"), "2024+": ("2024-01-01", None)}

    print(f"global semis narrative (SMH+SOXX+TSM) {MOM_WK}w-mom -> next-week CN basket return")
    print(f"weekly W-FRI · NW-HAC t (lags=4) · controls = SPY {MOM_WK}w-mom + CN-universe {MOM_WK}w-mom\n")
    hdr = f"{'basket':18}{'era':9}{'n':>4}{'uni_b':>8}{'uni_t':>7}{'uni_p':>7}{'mv_semis_t':>11}{'mv_spy_t':>9}{'mv_cn_t':>8}"
    print(hdr); print("-" * len(hdr))
    out = [hdr, "-" * len(hdr)]
    for bid in AI + PLACEBO:
        if bid not in bret:
            continue
        fwd = bret[bid].shift(-1)                                 # next-week return
        df = pd.concat({"fwd": fwd, "semis": semis_mom, "spy": spy_mom, "cn": cn_mom},
                       axis=1, sort=True).dropna()
        tag = "AI" if bid in AI else "placebo"
        for ename, (lo, hi) in eras.items():
            d = df.copy()
            if lo:
                d = d[d.index >= lo]
            if hi:
                d = d[d.index <= hi]
            if len(d) < 25:
                line = f"{bid:18}{ename:9}{len(d):>4}  (too few weeks)"
                print(line); out.append(line); continue
            uni = nw_ols(d["fwd"].values, [d["semis"].values], ["semis"])
            mv = nw_ols(d["fwd"].values, [d["semis"].values, d["spy"].values, d["cn"].values],
                        ["semis", "spy", "cn"])
            ub, ut, up = uni.get("semis", (np.nan, np.nan, np.nan))
            mst = mv.get("semis", (np.nan, np.nan, np.nan))[1]
            mspy = mv.get("spy", (np.nan, np.nan, np.nan))[1]
            mcn = mv.get("cn", (np.nan, np.nan, np.nan))[1]
            line = (f"{bid[:17]:18}{ename:9}{uni['_n']:>4}{ub:>8}{ut:>7}{up:>7}{mst:>11}{mspy:>9}{mcn:>8}")
            print(line); out.append(line)
        out.append("")
        print()

    rpt = root / "reports" / "china-global-theme.md"
    rpt.parent.mkdir(exist_ok=True)
    rpt.write_text(
        "# Does global AI-narrative momentum predict next-week CN AI-supply baskets?\n\n"
        f"EW {MOM_WK}w log-momentum of SMH+SOXX+TSM -> next-week EW return of each THS AI basket. "
        "Weekly W-FRI, Newey-West HAC t (lags=4). uni = univariate; mv = with SPY + CN-universe "
        f"{MOM_WK}w-mom controls (the horse race). Placebo = baijiu/gold/innovative-rx.\n\n"
        "KEY TEST = does the semis t survive in **pre-2024** (not just the 2024+ AI run)?\n\n"
        "```\n" + "\n".join(out) + "\n```\n")
    print(f"wrote {rpt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
