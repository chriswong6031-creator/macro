"""OKX retail positioning chips — Phase-0 honest skill harness (research-only).

The HARD GATE before either OKX rubik retail chip (long/short ACCOUNT ratio,
taker buy/sell flow) is allowed anywhere near scoring: does the chip carry a
FORWARD-RETURN edge on BTC — net of the multiple-testing (BH-FDR) and
selection (DSR) haircuts the rest of the book is held to — INCREMENTALLY over
the positioning incumbents we already show (funding-z + OI %ile)?

This is a SINGLE-ASSET TIME-SERIES test (one BTC series), NOT the cross-sectional
panel rank-IC of scripts.insider_phase0. The precedent is scripts.calibrate_vector
(local forward_returns(close, h) = close.shift(-h)/close - 1). We measure the
signal-vs-forward-return Spearman skill over the available window, both standalone
and after residualizing out funding-z + OI %ile (engine.validation.resid_z), then
deflate for multiplicity + selection.

HONEST PRIOR — stays DISPLAY. Two structural reasons:
  (a) rubik history is shallow (~180 daily rows for BTC), so the sample is tiny and
      a pre/post-2021 split-half is impossible — we split the AVAILABLE window.
  (b) crowding is a FRAGILITY/CONTEXT read, not a directional edge — the same
      single-asset-timing trap that flipped the carry signal and left the CME basis
      at rank-IC ~0 applies here.

Run: .venv/bin/python -m scripts.okx_retail_phase0
Writes reports/okx-retail-phase0.md. No engine edit, no wiring — pure harness.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")

from engine import btc_inputs, btc_signals  # noqa: E402
from engine.validation import (  # noqa: E402
    backtest_core, benjamini_hochberg, block_bootstrap_ci, deflated_sharpe,
    dsr_verdict, ic_summary, newey_west_tstat, rank_ic, resid_z, ret_moments,
)
from lib import config  # noqa: E402

# ----- fixed-form params (declared, NOT tuned to the result) ----------------- #
HORIZONS = [21, 63]          # forward-return windows (trading days)
IC_WIN = 30                  # rolling window length for the per-window IC series
IC_STEP = 7                  # window stride (shallow rubik history -> short stride)
RESID_WIN = 90               # rolling-OLS window for the causal residualization
RESID_MIN_P = 30             # min obs before a residual beta is estimable
COST_BPS = 10.0              # BTC one-way (spread+slippage), charged on |Δpos|
CONTRARIAN_Z = 1.0           # |z| band for the simplest tradable contrarian proxy
TRADING_YEAR = 365           # BTC trades every day


def forward_returns(close: pd.Series, horizons: list[int]) -> pd.DataFrame:
    """Local single-asset forward-return frame (calibrate_vector.py:54)."""
    return pd.DataFrame({h: close.shift(-h) / close - 1 for h in horizons})


def window_ics(sig: pd.Series, fwd: pd.Series, win: int = IC_WIN,
               step: int = IC_STEP) -> list[float]:
    """Per-window Spearman IC of `sig` vs `fwd` over overlapping windows — the
    single-asset analogue of the panel per-date IC (each window plays the role of
    a 'cross-section' of consecutive days). rank_ic needs >=10 joint points."""
    j = pd.concat([sig.rename("s"), fwd.rename("f")], axis=1).dropna()
    ics = []
    for lo in range(0, max(0, len(j) - win) + 1, step):
        w = j.iloc[lo: lo + win]
        ic = rank_ic(w["s"], w["f"])
        if np.isfinite(ic):
            ics.append(ic)
    return ics


def skill(sig: pd.Series, fwd_df: pd.DataFrame) -> dict:
    """Standalone skill of one signal at each horizon: full-sample Spearman IC (the
    interpretable headline) + the rolling-window IC summary with a HAC t-stat."""
    out = {}
    for h in HORIZONS:
        fwd = fwd_df[h]
        j = pd.concat([sig.rename("s"), fwd.rename("f")], axis=1).dropna()
        full_ic = (float(j["s"].rank().corr(j["f"].rank())) if len(j) >= 10
                   else float("nan"))
        ics = window_ics(sig, fwd)
        summ = ic_summary(ics, periods_per_year=max(1, 252 // h)) if ics else {"n": 0}
        # p-value for the FDR panel: HAC p of the mean window IC (falls back to the
        # full-sample sign test only when there are too few windows).
        p = summ.get("p_hac")
        out[h] = {"full_ic": round(full_ic, 4) if np.isfinite(full_ic) else None,
                  "n_obs": int(len(j)), "n_windows": int(summ.get("n", 0)),
                  "mean_ic": summ.get("mean_ic"), "ic_ir": summ.get("ic_ir"),
                  "t_hac": summ.get("t_hac"), "p": p, "hit": summ.get("hit")}
    return out


def split_half_signs(sig: pd.Series, fwd_df: pd.DataFrame) -> dict:
    """Sign of the full-sample Spearman IC on each half of the AVAILABLE window
    (a pre/post-2021 split is impossible at ~180 rows). 'robust' iff both halves
    share the full-sample sign at BOTH horizons."""
    out = {}
    for h in HORIZONS:
        j = pd.concat([sig.rename("s"), fwd_df[h].rename("f")], axis=1).dropna()
        if len(j) < 24:
            out[h] = {"first": None, "second": None, "same_sign": None}
            continue
        mid = len(j) // 2
        def ic(d):
            return float(d["s"].rank().corr(d["f"].rank())) if len(d) >= 10 else float("nan")
        a, b = ic(j.iloc[:mid]), ic(j.iloc[mid:])
        same = (np.isfinite(a) and np.isfinite(b) and np.sign(a) == np.sign(b)
                and a != 0 and b != 0)
        out[h] = {"first": round(a, 4) if np.isfinite(a) else None,
                  "second": round(b, 4) if np.isfinite(b) else None,
                  "same_sign": bool(same)}
    return out


def proxy_backtest(close: pd.Series, z: pd.Series, n_trials: int) -> dict:
    """Simplest tradable CONTRARIAN proxy on the retail long/short z: long/flat,
    long (+1) only when retail is crowded SHORT (z < -band, capitulation context),
    flat otherwise. Next-bar, cost-charged. DSR deflates for the honest trial count.
    Restricted to the OKX-available window so 4000+ pre-rubik flat days don't
    dilute the Sharpe to ~0 (the signal only spans ~180 days)."""
    valid = z.reindex(close.index).dropna()
    if valid.empty:
        return {"days_long": 0, "dsr": None}
    close = close.loc[valid.index[0]:]      # trade only where the signal exists
    alloc = pd.Series(0.0, index=close.index)
    zr = z.reindex(close.index)
    alloc[zr < -CONTRARIAN_Z] = 1.0
    bt = backtest_core(close, alloc, cost_bps=COST_BPS)
    m = ret_moments(bt["net"])
    days_long = int((alloc > 0).sum())
    if m is None:
        return {"days_long": days_long, "dsr": None}
    dsr = deflated_sharpe(m[0], m[1], m[2], m[3], n_trials=n_trials,
                          trading_year=TRADING_YEAR)
    ci = block_bootstrap_ci(bt["net"], block=21, ann=TRADING_YEAR)
    return {"days_long": days_long, "moments_n": m[3], "dsr": dsr, "boot_ci": ci}


def main() -> int:
    inputs = btc_inputs.load_all()
    if inputs.get("okx_ls_ratio") is None and inputs.get("okx_taker_buy") is None:
        print("no OKX rubik data — run `python -m scripts.collect --only okx` first")
        return 1
    sig = btc_signals.compute_all(inputs)
    close = sig["close"]
    fwd_df = forward_returns(close, HORIZONS)

    # display signals under test (NEVER scored)
    S = {"ls_ratio_z": sig.get("okx_ls_ratio_z"),
         "taker_buy": sig.get("okx_taker_buy")}
    S = {k: v for k, v in S.items() if v is not None}

    # ---- Step A: standalone skill -------------------------------------------- #
    standalone = {name: skill(s, fwd_df) for name, s in S.items()}

    # ---- Step B: incremental over the incumbents (funding-z + OI %ile) -------- #
    basis = [b for b in (sig.get("funding_z"), sig.get("oi_mcap_pctile")) if b is not None]
    resid_skill, resid_split = {}, {}
    if "ls_ratio_z" in S and basis:
        r = resid_z(S["ls_ratio_z"], basis=basis, win=RESID_WIN, min_p=RESID_MIN_P)
        resid_skill["ls_ratio_z|resid"] = skill(r, fwd_df)
        resid_split["ls_ratio_z|resid"] = split_half_signs(r, fwd_df)

    # ---- Step C: multiplicity (BH-FDR) over the whole screened panel ---------- #
    pvals = {}
    for name, byh in {**standalone, **resid_skill}.items():
        for h, d in byh.items():
            if d.get("p") is not None:
                pvals[f"{name}@{h}"] = d["p"]
    n_trials = max(len(pvals), len(S) * len(HORIZONS))   # honest trial count (~6-8)
    fdr = benjamini_hochberg(pvals, alpha=0.10) if pvals else {}

    # ---- tradable proxy + DSR + split-half ----------------------------------- #
    proxy = proxy_backtest(close, S["ls_ratio_z"], n_trials) if "ls_ratio_z" in S else {}
    splits = {name: split_half_signs(s, fwd_df) for name, s in S.items()}
    splits.update(resid_split)

    # ---- verdict ------------------------------------------------------------- #
    resid_fdr_survive = any(v.get("reject") for k, v in fdr.items() if "resid" in k)
    dsr_pass = bool(proxy.get("dsr") and proxy["dsr"]["dsr"] >= 0.90)
    resid_both_signs = bool(resid_split.get("ls_ratio_z|resid")
                            and all(d.get("same_sign") for d in resid_split["ls_ratio_z|resid"].values()))
    go = resid_fdr_survive and dsr_pass and resid_both_signs
    verdict = "GO (propose promotion in a SEPARATE follow-up)" if go else \
              "NO-GO / DISPLAY-ONLY (honest prior held)"

    # honest sample size = the OKX-aligned window, NOT the full BTC price history
    okx_span = next((s.dropna() for s in S.values() if s is not None), pd.Series(dtype=float))
    n_rows = int(len(okx_span))
    report = _render(standalone, resid_skill, fdr, proxy, splits, n_trials, verdict,
                     n_rows=n_rows, basis_ok=bool(basis))
    out = config.ROOT / config.load()["storage"]["reports_dir"] / "okx-retail-phase0.md"
    out.write_text(report)
    print(report)
    print(f"\n[report] {out}")
    print(f"[verdict] {verdict}")
    return 0


def _render(standalone, resid_skill, fdr, proxy, splits, n_trials, verdict,
            n_rows, basis_ok) -> str:
    L = ["# OKX retail positioning chips — Phase-0 (single-asset BTC skill)", "",
         f"**VERDICT: {verdict}**", "",
         f"Sample: {n_rows} daily rows of OKX rubik signal history (shallow). "
         f"Incumbent basis (funding-z + OI %ile) {'available' if basis_ok else 'MISSING'}. "
         f"Honest n_trials = {n_trials}.", "",
         "DISPLAY-ONLY chips: OKX retail long/short ACCOUNT ratio (z) + taker buy share. "
         "The gate asks whether either carries a forward-return edge INCREMENTAL over "
         "the funding-z + OI %ile incumbents, surviving BH-FDR(10%) and DSR>=0.90 with a "
         "sign-stable split-half. Honest prior: stays display.", ""]

    def skill_table(title, block):
        L.append(f"## {title}")
        L.append("| signal@h | full IC | n_obs | n_win | mean IC | IC-IR | t(HAC) | p | hit |")
        L.append("|---|---|---|---|---|---|---|---|---|")
        for name, byh in block.items():
            for h, d in byh.items():
                L.append(f"| {name}@{h} | {d['full_ic']} | {d['n_obs']} | {d['n_windows']} "
                         f"| {d['mean_ic']} | {d['ic_ir']} | {d['t_hac']} | {d['p']} | {d['hit']} |")
        L.append("")

    skill_table("Step A — standalone skill", standalone)
    if resid_skill:
        skill_table("Step B — INCREMENTAL (residual of ls-ratio-z on funding-z + OI %ile)",
                    resid_skill)

    L.append("## Step C — BH-FDR(10%) over the screened panel")
    if fdr:
        L.append("| test | p | q | reject |")
        L.append("|---|---|---|---|")
        for k, v in fdr.items():
            L.append(f"| {k} | {v['p']} | {v['q']} | {v['reject']} |")
    else:
        L.append("_too few windows for a HAC p-value panel (sample too short)._")
    L.append("")

    L.append("## Tradable contrarian proxy (long/flat: long only when retail crowded SHORT)")
    if proxy.get("dsr"):
        d = proxy["dsr"]
        L.append(f"- days long: {proxy['days_long']} · moments n: {proxy.get('moments_n')}")
        L.append(f"- Sharpe(daily): {d['sr_daily']} → annual {d['sr_annual']}; "
                 f"haircut SR0(annual) {d['sr0_annual']} @ n_trials={d['n_trials']}")
        L.append(f"- **DSR {d['dsr']}** → {dsr_verdict(d['dsr'])}")
        if proxy.get("boot_ci"):
            L.append(f"- block-bootstrap Sharpe CI: {proxy['boot_ci'].get('sharpe_ci')} "
                     f"(P[Sharpe>0]={proxy['boot_ci'].get('sharpe_gt0_prob')})")
    else:
        L.append("_proxy un-evaluable (signal/sample too short)._")
    L.append("")

    L.append("## Split-half sign stability (available window halved — pre-2021 impossible)")
    L.append("| signal | h | first-half IC | second-half IC | same sign |")
    L.append("|---|---|---|---|---|")
    for name, byh in splits.items():
        for h, d in byh.items():
            L.append(f"| {name} | {h} | {d['first']} | {d['second']} | {d['same_sign']} |")
    L.append("")
    L.append("---")
    L.append("GO requires: residual (incremental) IC survives BH-FDR(10%) AND DSR>=0.90 "
             "AND both split-halves same sign. Any failure → chip stays DISPLAY-ONLY "
             "(no engine change, no wiring). This script modifies nothing.")
    return "\n".join(L)


if __name__ == "__main__":
    sys.exit(main())
