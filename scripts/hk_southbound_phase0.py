"""HK southbound-vs-price DIVERGENCE — Phase 0 honest incremental harness.

Pre-registered question
-----------------------
Does the southbound-net-FLOW-vs-HSI-PRICE *divergence* read add INCREMENTAL
predictive content for forward HSI returns (21d / 63d) OVER the named incumbent —
HK breadth (`pct_above_50`, level + 20d slope) + southbound net LEVEL z — after
orthogonalizing the divergence signal against that incumbent?

Honest prior = **DISPLAY-ONLY.** The divergence is a derived interaction of two
things the incumbent already contains (southbound flow z, and price/breadth), and
southbound is ALREADY folded into `engine/hk_regime.liquidity_overlay`. So the
realistic expectation is ~zero incremental content. This mirrors the HK
residual-alpha kill (`scripts/hk_residual_alpha_phase0.py`). The binding constraint
is POWER: southbound only exists post-2014 (Connect era), so the overlap window is
~12 years of daily obs — flag n LOUDLY and degrade an underpowered result to
DISPLAY, never a spurious GO.

This is a SINGLE-ASSET time-series test (HSI level, no HK cross-section), so it uses
the time-series primitives in `engine/validation.py` (Newey-West, block bootstrap,
deflated Sharpe, BH-FDR) — NOT the cross-sectional rank_ic / quintile stack.

Run:
  .venv/bin/python -m scripts.hk_southbound_phase0            # score the on-disk stores
Writes reports/hk-southbound-divergence-phase0.md. No commit, no site build.
"""
from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")

from engine.validation import (block_bootstrap_ci, benjamini_hochberg,  # noqa: E402
                               deflated_sharpe, dsr_verdict,
                               newey_west_tstat, ret_moments)
from lib import config, store  # noqa: E402

WINDOW = 63          # ~one quarter; the flow-cum + price-return horizon (matches the chip)
Z_HI, RET_HI = 0.5, 0.02
MIN_N = 1500         # below this the overlap is underpowered → DISPLAY regardless


# --------------------------------------------------------------------------- #
# Construction helpers (causal — every standardization excludes the current row)
# --------------------------------------------------------------------------- #
def _z_causal(s: pd.Series, win: int = 252) -> pd.Series:
    """Rolling z using ONLY past data: mean/std over the window ending at t-1."""
    mu = s.rolling(win, min_periods=max(30, win // 4)).mean().shift(1)
    sd = s.rolling(win, min_periods=max(30, win // 4)).std().shift(1)
    return (s - mu) / sd.replace(0.0, np.nan)


def _ols_resid(y: pd.Series, X: pd.DataFrame) -> pd.Series:
    """Residual of y after OLS on [1, X] (Frisch-Waugh partialling)."""
    Xm = np.column_stack([np.ones(len(X)), X.values])
    beta, *_ = np.linalg.lstsq(Xm, y.values, rcond=None)
    return pd.Series(y.values - Xm @ beta, index=y.index)


def build_frame(window: int = WINDOW) -> pd.DataFrame | None:
    """Assemble the daily binding frame from the on-disk stores (overlap of
    southbound ∩ HSI ∩ HK breadth). All via store.read — never raw parquet paths."""
    sb = store.read("china_connect", "southbound")
    px = store.read("hk", "^HSI")
    br = store.read("hk_breadth", "breadth")
    if sb is None or "net" not in sb.columns or px is None or "close" not in px.columns:
        return None
    if br is None or "pct_above_50" not in br.columns:
        return None
    net = sb["net"].dropna()
    close = px["close"].dropna()
    breadth = br["pct_above_50"].dropna()

    # FLOW trend: window-cumulative southbound net, z vs its own causal 1y history
    cum = net.rolling(window).sum()
    flow_z = _z_causal(cum)
    # PRICE trend: trailing window return of HSI
    px_ret = close / close.shift(window) - 1.0
    # incumbent predictors (causal z)
    breadth_lvl_z = _z_causal(breadth)
    breadth_slope_z = _z_causal(breadth.diff(20))
    sb_level_z = flow_z          # the window-cum southbound z — the SAME flow_z, per spec

    # forward (overlapping) HSI returns — the targets
    fwd21 = close.shift(-21) / close - 1.0
    fwd63 = close.shift(-63) / close - 1.0

    # divergence interactions (continuous): sign-agreement and magnitude
    div_sign = np.sign(flow_z) * np.sign(px_ret)
    div_mag = flow_z * px_ret

    # discrete state (mirrors the chip leaf) → for the realized overlay
    flow_up, flow_dn = flow_z >= Z_HI, flow_z <= -Z_HI
    px_up, px_dn = px_ret >= RET_HI, px_ret <= -RET_HI
    confirms = (flow_up & px_up) | (flow_dn & px_dn)

    df = pd.DataFrame({
        "close": close, "breadth_lvl_z": breadth_lvl_z, "breadth_slope_z": breadth_slope_z,
        "sb_level_z": sb_level_z, "flow_z": flow_z, "px_ret": px_ret,
        "div_sign": div_sign, "div_mag": div_mag,
        "fwd21": fwd21, "fwd63": fwd63,
        "confirms": confirms.astype(float), "flow_up": flow_up.astype(float),
    }).sort_index()
    # bind to the southbound (Connect-era) span on a common daily grid
    df = df.loc[net.index.min():]
    return df


# --------------------------------------------------------------------------- #
# The incremental test (no shared helper — built explicitly here)
# --------------------------------------------------------------------------- #
INCUMBENT = ["breadth_lvl_z", "breadth_slope_z", "sb_level_z"]


def _incr(d: pd.DataFrame, divcol: str, fwdcol: str, lags: int) -> dict:
    """Partial (incremental) test: orthogonalize BOTH the forward return and the
    divergence signal against the incumbent, then HAC-test the mean of their product
    (the Frisch-Waugh moment condition for a non-zero partial slope)."""
    cols = [divcol, fwdcol] + INCUMBENT
    s = d[cols].replace([np.inf, -np.inf], np.nan).dropna()
    if len(s) < 200:
        return {"n": int(len(s)), "t": None, "p": None, "mean": None}
    Xinc = s[INCUMBENT]
    e = _ols_resid(s[fwdcol], Xinc)            # forward return, incumbent removed
    g = _ols_resid(s[divcol], Xinc)            # divergence signal, incumbent removed
    nw = newey_west_tstat(g * e, lags=lags)    # mean(g·e)=0  <=>  partial slope=0
    return {"n": int(len(s)), "t": nw["t"], "p": nw["p"], "mean": nw["mean"]}


def run(window: int = WINDOW) -> dict:
    df = build_frame(window)
    if df is None:
        return {"error": "missing southbound / HSI / breadth store"}
    n = int(df[INCUMBENT + ["fwd21"]].dropna().shape[0])
    span = f"{df.index.min().date()}→{df.index.max().date()}"

    trials = [("div_sign", "fwd21", 21), ("div_sign", "fwd63", 63),
              ("div_mag", "fwd21", 21), ("div_mag", "fwd63", 63)]
    rows, pvals = {}, {}
    half = df.index[len(df) // 2]
    for divcol, fwdcol, lags in trials:
        key = f"{divcol}·{fwdcol}"
        full = _incr(df, divcol, fwdcol, lags)
        h1 = _incr(df.loc[:half], divcol, fwdcol, lags)
        h2 = _incr(df.loc[half:], divcol, fwdcol, lags)
        full["h1_t"], full["h2_t"] = h1["t"], h2["t"]
        # split-half robust = both halves significant AND same sign as each other
        full["split_robust"] = bool(
            h1["t"] is not None and h2["t"] is not None
            and abs(h1["t"]) > 1.96 and abs(h2["t"]) > 1.96
            and np.sign(h1["mean"] or 0) == np.sign(h2["mean"] or 0))
        rows[key] = full
        if full["p"] is not None:
            pvals[key] = full["p"]

    fdr = benjamini_hochberg(pvals, alpha=0.10)
    for k, q in fdr.items():
        rows[k]["q"] = q["q"]
        rows[k]["fdr_reject"] = q["reject"]

    overlay = _overlay(df, n_trials=len(trials))
    incr_go = any(r.get("p") is not None and r["p"] < 0.05 and r.get("fdr_reject")
                  and r.get("split_robust") for r in rows.values())
    dsr_go = overlay.get("dsr") is not None and overlay["dsr"] >= 0.90
    boot = overlay.get("boot", {})
    boot_go = (boot.get("sharpe_gt0_prob", 0) >= 0.90
               and overlay.get("maxdd_ok", False))
    power_ok = n >= MIN_N
    go = bool(power_ok and incr_go and dsr_go and boot_go)
    return {"span": span, "n": n, "window": window, "rows": rows, "overlay": overlay,
            "power_ok": power_ok, "incr_go": incr_go, "dsr_go": dsr_go, "boot_go": boot_go,
            "go": go}


def _overlay(df: pd.DataFrame, n_trials: int) -> dict:
    """Realized honest overlay: long HSI when divergence=='confirms' & flow accelerating
    IN, flat otherwise; daily-rebalanced. Report the EXCESS-over-buy-and-hold timing
    alpha (DSR + block-bootstrap), and whether its max-DD beats buy-and-hold's."""
    d = df.dropna(subset=["close", "confirms", "flow_up"]).copy()
    if len(d) < 200:
        return {"n": int(len(d))}
    hsi_ret = d["close"].pct_change(fill_method=None).fillna(0.0)
    pos = ((d["confirms"] > 0) & (d["flow_up"] > 0)).astype(float)
    strat = pos.shift(1).fillna(0.0) * hsi_ret      # enter next day (no look-ahead)
    excess = (strat - hsi_ret).dropna()             # timing alpha vs always-in B&H
    if len(excess) < 200:
        return {"n": int(len(excess))}

    def _maxdd(r: pd.Series) -> float:
        eq = (1.0 + r).cumprod()
        return float((eq / eq.cummax() - 1.0).min())

    mom = ret_moments(excess)
    dsr = deflated_sharpe(mom[0], mom[1], mom[2], mom[3], n_trials=max(n_trials, 1),
                          trading_year=252) if mom else None
    boot = block_bootstrap_ci(excess, block=21, ann=252)
    bh_dd, strat_dd = _maxdd(hsi_ret), _maxdd(strat)
    sr_ann = round(float(mom[0]) * np.sqrt(252), 2) if mom else None
    return {
        "n": int(len(excess)),
        "exposure_pct": round(100.0 * float(pos.mean()), 1),
        "excess_sr_ann": sr_ann,
        "bh_sr_ann": round(float(hsi_ret.mean() / hsi_ret.std() * np.sqrt(252)), 2),
        "dsr": dsr["dsr"] if dsr else None,
        "verdict": dsr_verdict(dsr["dsr"]) if dsr else None,
        "boot": boot,
        "bh_maxdd_pct": round(bh_dd * 100, 1), "strat_maxdd_pct": round(strat_dd * 100, 1),
        "maxdd_ok": bool(strat_dd >= bh_dd),     # less-negative = not worse
        "n_trials": n_trials,
    }


def verdict(r: dict) -> str:
    if r.get("error"):
        return f"[verdict] inconclusive — {r['error']}"
    if not r["power_ok"]:
        return (f"[verdict] UNDERPOWERED → DISPLAY-ONLY — only n={r['n']} overlap obs "
                f"(< {MIN_N}); southbound is Connect-era (post-2014), too short to "
                "promote a derived interaction. Ship as descriptive context.")
    if r["go"]:
        return ("[verdict] GO (review) — cleared incremental-FDR + DSR + bootstrap + "
                "split-half. Re-examine before wiring; the prior was DISPLAY.")
    return ("[verdict] DISPLAY-ONLY — the divergence read adds no robust INCREMENTAL "
            "content over breadth + southbound-level. It is a derived interaction of "
            "inputs the incumbent already holds (and southbound already feeds "
            "liquidity_overlay). Ship the chip as positioning-vs-price context, not a "
            "scored leg.")


def render(r: dict) -> str:
    L = ["# HK southbound-vs-price divergence — Phase 0 (incremental, single-asset TS)", "",
         "*Generated by `scripts/hk_southbound_phase0.py`. Pre-registered question: does the "
         "southbound-FLOW-vs-HSI-PRICE divergence add INCREMENTAL predictive content for forward "
         "HSI returns (21/63d) over the incumbent — HK breadth (`pct_above_50` level + 20d slope) + "
         "southbound net LEVEL z — after orthogonalizing the divergence against that incumbent? "
         "Honest prior: DISPLAY-ONLY (the divergence is a derived interaction of inputs the "
         "incumbent already contains; southbound already feeds `liquidity_overlay`).*", ""]
    if r.get("error"):
        return "\n".join(L + [f"_inconclusive — {r['error']}_", ""])
    L += [f"**{verdict(r)}**", "",
          f"Binding overlap span **{r['span']}** · effective n = **{r['n']}** daily obs "
          f"(power floor {MIN_N}; southbound = Connect-era post-2014) · window {r['window']}d.", ""]
    if not r["power_ok"]:
        L += [f"> ⚠️ **Underpowered:** n={r['n']} < {MIN_N}. An underpowered read degrades to "
              "DISPLAY, never a spurious GO (same trap as the HK residual-alpha 3y read).", ""]
    L += ["## Incremental test (Frisch-Waugh partial slope, Newey-West HAC)", "",
          "| trial | incr t_HAC | p | q_FDR | FDR✓ | half-1 t | half-2 t | split✓ | n |",
          "|---|--:|--:|--:|:--:|--:|--:|:--:|--:|"]
    for k, v in r["rows"].items():
        L.append(f"| {k} | {v.get('t')} | {v.get('p')} | {v.get('q', '—')} "
                 f"| {'✓' if v.get('fdr_reject') else '·'} | {v.get('h1_t')} | {v.get('h2_t')} "
                 f"| {'✓' if v.get('split_robust') else '·'} | {v.get('n')} |")
    o = r["overlay"]
    boot = o.get("boot", {})
    L += ["", "## Realized overlay (long HSI on confirms & flow-in, else flat) — EXCESS vs buy-and-hold", "",
          f"- Exposure (time in market): **{o.get('exposure_pct')}%**",
          f"- Excess Sharpe (ann): **{o.get('excess_sr_ann')}**  ·  buy-and-hold Sharpe: {o.get('bh_sr_ann')}",
          f"- Deflated Sharpe (n_trials={o.get('n_trials')}): **{o.get('dsr')}** — {o.get('verdict')}",
          f"- Block-bootstrap Sharpe 95% CI: {boot.get('sharpe_ci')}  ·  P(SR>0) = {boot.get('sharpe_gt0_prob')}",
          f"- Max-drawdown: strat {o.get('strat_maxdd_pct')}% vs buy-and-hold {o.get('bh_maxdd_pct')}% "
          f"({'not worse' if o.get('maxdd_ok') else 'WORSE'})", "",
          "## GO bar (must clear ALL, else DISPLAY)", "",
          f"- Power n ≥ {MIN_N}: **{'PASS' if r['power_ok'] else 'FAIL'}**",
          f"- Incremental p<0.05 + survives BH-FDR + split-half robust (≥1 horizon): "
          f"**{'PASS' if r['incr_go'] else 'FAIL'}**",
          f"- Overlay DSR ≥ 0.90: **{'PASS' if r['dsr_go'] else 'FAIL'}**",
          f"- Bootstrap P(SR>0) ≥ 0.90 AND max-DD not worse than B&H: "
          f"**{'PASS' if r['boot_go'] else 'FAIL'}**", "",
          "---", "",
          "**How to read.** The incremental test partials the incumbent (breadth + southbound "
          "LEVEL) out of BOTH the forward return and the divergence signal, then HAC-tests whether "
          "what's left co-moves — the honest 'does divergence add anything new?' question. The "
          "overlay is the tradable realization: does timing HSI exposure on the 'confirms' state "
          "beat simply holding? Divergence is built from inputs the incumbent already owns, so the "
          "expected (and prior) answer is no incremental edge → ship as DISPLAY context.", ""]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", type=int, default=WINDOW)
    args = ap.parse_args()
    r = run(args.window)
    out = config.ROOT / config.load()["storage"]["reports_dir"] / "hk-southbound-divergence-phase0.md"
    out.write_text(render(r))
    print(f"[report] {out}\n{verdict(r)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
