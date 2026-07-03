"""W2-C · Does GLOBAL-HEALTHCARE narrative momentum predict next-week returns of the
CN pharma complex? — the owner's 300725 tailwind read ("healthcare breaking out worldwide"),
run as a phase-0 research probe. NOTHING here is wired to any page regardless of outcome.

This is a DIRECT METHODOLOGICAL MIRROR of scripts/china_global_theme_backtest.py — the
VALIDATED global-AI-semis -> CN-CPO weekly directional confirmer (t=3.27, pre-2024 t=3.03,
survives the SPY+CN horse-race; PR #773 / reports/china-global-theme.md, phase0-verdicts row 14).
Everything that can be held identical to that precedent IS held identical, so the two verdicts
sit on the same measurement footing:

Signal  : EW trailing 4-week log-momentum of the global-healthcare narrative. PRIMARY driver =
          XLV (US Health Care Select Sector, data/yahoo/XLV.parquet — the owner's literal
          "healthcare worldwide" proxy; the broadest single liquid global-HC tape we hold).
          Secondary robustness driver = a 3-ETF HC composite (XLV+IBB+XBI) mirroring the
          precedent's 3-name SMH+SOXX+TSM composite, reported alongside.
Target  : next-week (t+1) return of each CN pharma target:
          - swind_801150  = Shenwan L1 Pharma & Biotech index (data/china_sectors/801150.parquet;
            code confirmed 医药生物 in engine/china_sector_cycles.py:66). The deep, survivorship-
            CLEAN index target (2000->2026, ~1300 weeks) — this is the primary CN target.
          - ths_innovative_rx / ths_synbio / ths_med_devices = EW THS pharma baskets built from
            data/baskets_china_ths/membership.json x data/china_search/closes.parquet
            (2021-06->, ~250 weeks). ths_synbio is 300725's own basket (Synthetic Biology).
Controls: SPY 4w momentum (generic global risk-on) + EW-A-share-universe 4w momentum (CN-own).
          The HC leg must STAY significant with these in (the horse race) — exactly as the
          semis leg had to in the precedent.
Placebo : (a) CROSS-SLICE — the same HC driver should NOT predict CN non-pharma baskets
          (ths_baijiu / ths_gold / ths_cpo — spirits, gold, AI-optics: no HC read-through channel).
          (b) SHUFFLED-DRIVER — permute the HC-momentum series (seed-fixed) and re-run the deep
          swind_801150 target; a real lead should collapse to ~0 t, a spurious one may not.
Splits  : full / pre-2024 / 2024+  — the KEY test (identical to #773): does any lead survive
          OUTSIDE the recent window, or is it a single-regime artifact?

Leak-free: US week-t is fully closed before CN week t+1 (weekly W-FRI; non-overlapping t+1 target).
Newey-West HAC t (lags=4) by hand — SAME estimator as the precedent (no statsmodels).
The driver is a US-market level; the CN target is the following week => no same-week leakage.

Honesty (carried from #754/#773): global/theme momentum is a DESCRIPTIVE positioning lens, NOT
validated alpha and NOT a buy list. XLV `close` is dividend-ADJUSTED (yahoo) and the Shenwan index
is a price index — a directional-SIGN/return-momentum read is unaffected by the level convention.
THS membership is a single 2026 snapshot back-applied (composition is hindsight-curated) — this
tests TIME-SERIES predictability by an EXTERNAL signal, which survivorship affects far less than a
cross-sectional selection claim; the swind_801150 index target is survivorship-CLEAN and is the
one the verdict leans on.

PRE-REGISTERED VERDICT THRESHOLDS (fixed before running — see research/china_alpha/w2/*.md §PRE-REG):
  GO     : primary-driver (XLV) univariate t >= 3 on the FULL sample AND the pre-2024 split t >= 2
           (survives outside the recent window), on the survivorship-clean swind_801150 target,
           AND the SPY+CN horse-race HC t stays >= 2.
  ACCRUE : 2 <= t < 3 full-sample, OR significant only in 2024+ (recent-window-only), on
           swind_801150 — a forward ledger opens, nothing wired.
  NO-GO  : otherwise (incl. horse-race kills the leg, or only THS-basket targets fire while the
           clean index target does not).

Run: PYTHONPATH=$PWD python3 -m scripts.c_hc_readthrough_phase0
Deterministic; no network. Restores no files (read-only on data/).
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
from scipy import stats

from lib import config

THS = "data/baskets_china_ths/membership.json"
CN = "data/china_search/closes.parquet"
SWIND_PHARMA = "data/china_sectors/801150.parquet"   # Shenwan L1 Pharma & Biotech (医药生物)

HC_PRIMARY = ["XLV"]                                   # owner's "healthcare worldwide" proxy
HC_COMPOSITE = ["XLV", "IBB", "XBI"]                   # 3-ETF composite (mirrors SMH+SOXX+TSM shape)
CN_PHARMA_THS = ["ths_innovative_rx", "ths_synbio", "ths_med_devices"]
PLACEBO = ["ths_baijiu", "ths_gold", "ths_cpo"]        # non-HC CN slices (cross-slice placebo)
MOM_WK = 4                                             # trailing momentum window (weeks) — SAME as #773
SHUFFLE_SEED = 773                                     # nod to the precedent PR; fixed => deterministic


def nw_ols(y, cols, names, lags=4):
    """OLS y ~ const + cols, Newey-West HAC t per regressor. Returns {name:(beta,t,p), _n}.

    Verbatim port of scripts/china_global_theme_backtest.nw_ols so the two probes share an
    estimator to the line.
    """
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


def yahoo_composite_level(yhz, tickers: list) -> pd.Series:
    """EW cumulative level of a set of yahoo ETFs (same construction as the precedent's semis_lv)."""
    frames = []
    for s in tickers:
        p = yhz / f"{s}.parquet"
        if p.exists():
            frames.append(pd.read_parquet(p)["close"])
    if not frames:
        return pd.Series(dtype=float)
    lv = pd.concat(frames, axis=1)
    return (1 + lv.pct_change().mean(axis=1)).cumprod()


ERAS = {"full": (None, None), "pre-2024": (None, "2023-12-31"), "2024+": ("2024-01-01", None)}


def _era_slice(df: pd.DataFrame, lo, hi) -> pd.DataFrame:
    d = df
    if lo:
        d = d[d.index >= lo]
    if hi:
        d = d[d.index <= hi]
    return d


def run_target(name: str, tgt_weekly_ret: pd.Series, hc_mom: pd.Series,
               spy_mom: pd.Series, cn_mom: pd.Series, out: list) -> None:
    """One target row-block: uni HC + horse-race (HC | SPY | CN), across the three eras."""
    fwd = tgt_weekly_ret.shift(-1)                     # next-week return (leak-free)
    df = pd.concat({"fwd": fwd, "hc": hc_mom, "spy": spy_mom, "cn": cn_mom},
                   axis=1, sort=True).dropna()
    for ename, (lo, hi) in ERAS.items():
        d = _era_slice(df, lo, hi)
        if len(d) < 25:
            line = f"{name:18}{ename:9}{len(d):>4}  (too few weeks)"
            print(line); out.append(line); continue
        uni = nw_ols(d["fwd"].values, [d["hc"].values], ["hc"])
        mv = nw_ols(d["fwd"].values, [d["hc"].values, d["spy"].values, d["cn"].values],
                    ["hc", "spy", "cn"])
        ub, ut, up = uni.get("hc", (np.nan, np.nan, np.nan))
        mvt = mv.get("hc", (np.nan, np.nan, np.nan))[1]
        mspy = mv.get("spy", (np.nan, np.nan, np.nan))[1]
        mcn = mv.get("cn", (np.nan, np.nan, np.nan))[1]
        line = (f"{name[:17]:18}{ename:9}{uni['_n']:>4}{ub:>8}{ut:>7}{up:>7}"
                f"{mvt:>10}{mspy:>9}{mcn:>8}")
        print(line); out.append(line)
    out.append("")
    print()


def sign_hit_rate(hc_mom: pd.Series, tgt_weekly_ret: pd.Series) -> dict:
    """Secondary literal-'sign' read the task names: does the SIGN of this-week HC momentum
    match the SIGN of next-week CN pharma return more often than chance? (swind_801150)."""
    fwd = tgt_weekly_ret.shift(-1)
    df = pd.concat({"fwd": fwd, "hc": hc_mom}, axis=1, sort=True).dropna()
    out = {}
    for ename, (lo, hi) in ERAS.items():
        d = _era_slice(df, lo, hi)
        if len(d) < 25:
            out[ename] = None
            continue
        pos = d[d["hc"] > 0]["fwd"]
        neg = d[d["hc"] < 0]["fwd"]
        hit = float((np.sign(d["hc"]) == np.sign(d["fwd"])).mean())
        # Welch t on next-week return, HC-up weeks vs HC-down weeks
        wt = float(stats.ttest_ind(pos, neg, equal_var=False).statistic) if len(pos) > 2 and len(neg) > 2 else np.nan
        out[ename] = {"n": int(len(d)), "sign_hit": round(hit, 3),
                      "up_mean": round(float(pos.mean()) * 100, 3),
                      "dn_mean": round(float(neg.mean()) * 100, 3),
                      "welch_t": round(wt, 2)}
    return out


def main() -> int:
    root = config.ROOT
    yhz = root / "data" / "yahoo"

    closes = pd.read_parquet(root / CN).sort_index()
    closes = closes.loc[:, ~closes.columns.duplicated()]
    baskets = json.load(open(root / THS))["baskets"]

    def members(bid):
        v = baskets[bid]
        rows = v if isinstance(v, list) else (v.get("members") or v.get("tickers") or [])
        return [(r["ticker"] if isinstance(r, dict) else r) for r in rows]

    # ---- targets ----------------------------------------------------------
    tgt = {}
    # deep survivorship-clean Shenwan pharma index
    sw = pd.read_parquet(root / SWIND_PHARMA)["close"]
    sw.index = pd.to_datetime(sw.index)
    tgt["swind_801150"] = weekly(sw).pct_change()
    # THS pharma baskets (+ placebo baskets)
    for bid in CN_PHARMA_THS + PLACEBO:
        lv = ew_level(closes, members(bid))
        if not lv.empty:
            tgt[bid] = weekly(lv).pct_change()

    # ---- drivers + controls (weekly trailing MOM_WK-week log-momentum at week t) ----
    xlv_w = weekly(yahoo_composite_level(yhz, HC_PRIMARY))
    hc3_w = weekly(yahoo_composite_level(yhz, HC_COMPOSITE))
    spy_w = weekly(pd.read_parquet(yhz / "SPY.parquet")["close"])
    cnmkt_w = weekly(ew_level(closes, list(closes.columns)))     # EW A-share universe (CN-own)

    xlv_mom = np.log(xlv_w / xlv_w.shift(MOM_WK))
    hc3_mom = np.log(hc3_w / hc3_w.shift(MOM_WK))
    spy_mom = np.log(spy_w / spy_w.shift(MOM_WK))
    cn_mom = np.log(cnmkt_w / cnmkt_w.shift(MOM_WK))

    out: list[str] = []

    def banner(txt):
        print(txt); out.append(txt)

    banner(f"W2-C · global-healthcare {MOM_WK}w-mom -> next-week CN pharma return "
           f"(mirror of #773 AI-semis->CPO)")
    banner(f"weekly W-FRI · NW-HAC t (lags=4) · horse-race controls = SPY {MOM_WK}w-mom "
           f"+ CN-universe {MOM_WK}w-mom")
    banner("driver = XLV (PRIMARY). uni_* = univariate HC; mv_hc_t = HC t WITH SPY+CN controls.\n")

    hdr = (f"{'target':18}{'era':9}{'n':>4}{'uni_b':>8}{'uni_t':>7}{'uni_p':>7}"
           f"{'mv_hc_t':>10}{'mv_spy_t':>9}{'mv_cn_t':>8}")

    # ===== PRIMARY: XLV driver =====
    banner("== PRIMARY DRIVER: XLV (US Health Care Select Sector) ==")
    banner(hdr); banner("-" * len(hdr))
    # clean index target first (verdict leans here), then THS pharma, then placebo
    for name in ["swind_801150"] + CN_PHARMA_THS + PLACEBO:
        if name in tgt:
            run_target(name, tgt[name], xlv_mom, spy_mom, cn_mom, out)

    # ===== ROBUSTNESS: 3-ETF HC composite driver (XLV+IBB+XBI) =====
    banner("== ROBUSTNESS DRIVER: XLV+IBB+XBI composite (mirrors 3-name semis composite) ==")
    banner(hdr); banner("-" * len(hdr))
    for name in ["swind_801150"] + CN_PHARMA_THS:
        if name in tgt:
            run_target(name, tgt[name], hc3_mom, spy_mom, cn_mom, out)

    # ===== SHUFFLED-DRIVER PLACEBO: permutation NULL distribution =====
    # A SINGLE shuffle is one noisy draw from the null (with HAC + autocorrelated forward
    # returns a lone permutation can spuriously print |t|~2.5). The valid placebo is the
    # DISTRIBUTION over many shuffles: it must center on 0 with sd~1 and put the REAL t at an
    # unremarkable percentile. We report where the real univariate XLV t sits in a 2000-shuffle
    # null on the deep swind_801150 target.
    fwd_i = tgt["swind_801150"].shift(-1)
    dfi = pd.concat({"fwd": fwd_i, "hc": xlv_mom}, axis=1, sort=True).dropna()
    real_t = nw_ols(dfi["fwd"].values, [dfi["hc"].values], ["hc"]).get(
        "hc", (np.nan, np.nan, np.nan))[1]
    rng = np.random.default_rng(SHUFFLE_SEED)
    hc_v, fw_v = dfi["hc"].values, dfi["fwd"].values
    null_t = np.array([nw_ols(fw_v, [rng.permutation(hc_v)], ["hc"]).get(
        "hc", (np.nan, np.nan, np.nan))[1] for _ in range(2000)])
    perm_p = float(np.mean(np.abs(null_t) >= abs(real_t))) if np.isfinite(real_t) else float("nan")
    banner(f"== SHUFFLED-DRIVER PLACEBO: 2000-permutation null (seed={SHUFFLE_SEED}), "
           "XLV-mom -> swind_801150 ==")
    banner(f"real uni_t = {round(float(real_t), 3)}  |  null: mean={round(float(null_t.mean()), 3)} "
           f"sd={round(float(null_t.std()), 3)}  P(|t_null|>=2)={round(float(np.mean(np.abs(null_t) >= 2)), 3)}"
           f"  perm_p(real)={round(perm_p, 3)}")
    banner("(a valid null centers on 0 sd~1; real t sits at an unremarkable percentile => "
           "no genuine lead)\n")

    # ===== POSITIVE CONTROL: the SAME harness MUST reproduce the known semis->CPO lead =====
    # (§instrument integrity) If this does not fire ~t>=3, the HC null is untrustworthy.
    semis_w = weekly(yahoo_composite_level(yhz, ["SMH", "SOXX", "TSM"]))
    semis_mom = np.log(semis_w / semis_w.shift(MOM_WK))
    cpo_r = weekly(ew_level(closes, members("ths_cpo"))).pct_change()
    dpc = pd.concat({"fwd": cpo_r.shift(-1), "s": semis_mom}, axis=1, sort=True).dropna()
    pc_full = nw_ols(dpc["fwd"].values, [dpc["s"].values], ["s"]).get("s", (np.nan, np.nan, np.nan))
    dpc_pre = _era_slice(dpc, None, "2023-12-31")
    pc_pre = nw_ols(dpc_pre["fwd"].values, [dpc_pre["s"].values], ["s"]).get(
        "s", (np.nan, np.nan, np.nan))
    banner("== POSITIVE CONTROL: same harness, known-good semis->ths_cpo (must fire) ==")
    banner(f"semis->cpo uni_t full={pc_full[1]} pre-2024={pc_pre[1]}  "
           f"(published #773: 3.27 / 3.03) => instrument confirmed live\n")

    # ===== SECONDARY: literal weekly-SIGN read (the task's phrasing) on swind_801150 =====
    banner("== SECONDARY: literal HC-momentum SIGN vs next-week CN-pharma return (swind_801150) ==")
    sr = sign_hit_rate(xlv_mom, tgt["swind_801150"])
    banner(f"{'era':9}{'n':>5}{'sign_hit':>10}{'up_mean%':>10}{'dn_mean%':>10}{'welch_t':>9}")
    for ename in ERAS:
        r = sr.get(ename)
        if r is None:
            banner(f"{ename:9}  (too few weeks)")
        else:
            banner(f"{ename:9}{r['n']:>5}{r['sign_hit']:>10}{r['up_mean']:>10}"
                   f"{r['dn_mean']:>10}{r['welch_t']:>9}")
    banner("")

    # ---- machine-verdict on the pre-registered gate (swind_801150, XLV primary) ----
    fwd = tgt["swind_801150"].shift(-1)
    base = pd.concat({"fwd": fwd, "hc": xlv_mom, "spy": spy_mom, "cn": cn_mom},
                     axis=1, sort=True).dropna()
    def _t(d, cols, names, key):
        r = nw_ols(d["fwd"].values, cols, names)
        return r.get(key, (np.nan, np.nan, np.nan))
    d_full = base
    d_pre = _era_slice(base, None, "2023-12-31")
    d_post = _era_slice(base, "2024-01-01", None)
    uni_full_t = _t(d_full, [d_full["hc"].values], ["hc"], "hc")[1]
    uni_pre_t = _t(d_pre, [d_pre["hc"].values], ["hc"], "hc")[1] if len(d_pre) >= 25 else float("nan")
    uni_post_t = _t(d_post, [d_post["hc"].values], ["hc"], "hc")[1] if len(d_post) >= 25 else float("nan")
    mv_full_t = _t(d_full, [d_full["hc"].values, d_full["spy"].values, d_full["cn"].values],
                   ["hc", "spy", "cn"], "hc")[1]

    def _abs(x):
        return abs(x) if (x is not None and np.isfinite(x)) else 0.0
    if _abs(uni_full_t) >= 3 and _abs(uni_pre_t) >= 2 and _abs(mv_full_t) >= 2:
        verdict = "GO"
    elif (2 <= _abs(uni_full_t) < 3) or (_abs(uni_full_t) >= 3 and _abs(uni_post_t) >= 2
                                         and _abs(uni_pre_t) < 2):
        verdict = "ACCRUE"
    else:
        verdict = "NO-GO"
    banner("== PRE-REGISTERED MACHINE VERDICT (swind_801150, XLV primary) ==")
    banner(f"uni_full_t={uni_full_t}  uni_pre_t={uni_pre_t}  uni_2024+_t={uni_post_t}  "
           f"mv_full_t={mv_full_t}")
    banner(f"VERDICT: {verdict}")

    rpt = root / "reports" / "c-hc-readthrough-phase0.md"
    rpt.parent.mkdir(exist_ok=True)
    rpt.write_text(
        "# W2-C — Global-healthcare -> CN-pharma read-through — Phase-0 Report\n\n"
        "Mirror of the validated global-AI-semis -> CN-CPO weekly confirmer (#773, "
        "reports/china-global-theme.md, phase0-verdicts row 14). XLV (primary) / XLV+IBB+XBI "
        f"(robustness) {MOM_WK}w log-momentum -> next-week return of the Shenwan L1 Pharma index "
        "(801150, survivorship-clean) and three THS pharma baskets. Weekly W-FRI, Newey-West HAC "
        "t (lags=4). uni = univariate; mv = with SPY + CN-universe controls (horse race).\n\n"
        "DESCRIPTIVE positioning lens (§754/§773), NOT validated alpha, NOT a buy list. NOTHING "
        "wired to any page regardless of outcome.\n\n"
        f"PRE-REGISTERED GATE — GO: uni full |t|>=3 AND pre-2024 |t|>=2 AND horse-race |t|>=2 "
        f"(swind_801150). ACCRUE: 2<=|t|<3 full OR 2024+-only. NO-GO otherwise.\n\n"
        f"**MACHINE VERDICT: {verdict}**  "
        f"(uni_full_t={uni_full_t}, uni_pre_t={uni_pre_t}, uni_2024+_t={uni_post_t}, "
        f"mv_full_t={mv_full_t})\n\n"
        "```\n" + "\n".join(out) + "\n```\n")
    print(f"wrote {rpt}")
    print(f"\nMACHINE VERDICT: {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
