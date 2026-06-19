"""Phase-0: International macro-timed equity sleeves (JP / EZ / GB / KR) — READ-ONLY research.

PORTS the S&P/Macro Vector scored archetype (macro-drawdown-timing long/flat
equity-vs-bills, scored on Sharpe + MaxDD reduction, NOT CAGR) to four ex-US
markets, plus a pooled equal-risk "Intl Macro Vector" sleeve.

PER MARKET  {JP -> _N225, EZ -> _STOXX50E (fallback _GDAXI for length), GB -> _FTSE,
KR -> _KS11}: build a LEAN macro de-risk gate from the monthly series on disk:
  (1) CURVE  : (yield_10y - short_3m) < 0  (inversion) -> de-risk leg
  (2) SAHM   : unemployment 3m-avg minus trailing-12m-min >= 0.5pp -> de-risk leg
  (3) SHORT  : short_3m rising (3m change > 0) AND level above its 12m mean
               (a tightening short-rate, the policy-restrictiveness leg)
alloc = 1.0 risk-on; glide toward bills (cash_yield = local short_3m) as legs fire
(half-off at >=1 leg, flat at >=2 legs — the lean composite). LAG: macro is monthly
and dated period-start, so we shift it forward 1 MONTH (publication lag, honest >=1m),
ffill to daily; the backtest's shift(1) then acts the position NEXT bar (no look-ahead).
Cash-credit the flat sleeve with the LOCAL short_3m.

VALIDATE per market AND pooled vs
  (a) local buy & hold,
  (b) local 200dma long/flat (the standard dumb trend baseline),
  (c) a DUMB single-leg curve-inversion gate (prove the composite adds over it).
GATES: deflated_sharpe (n_trials = markets x gate-variants, HONEST), same-sign
split-half, leave-one-crisis-out (drop each market's named bear, re-score).
HONEST-N = independent crises per market (~3-5) is the binding constraint.

SCORED only if a market (or pooled) clears: DSR >= 0.90 (>=0.95 survives) AND
beats the dumb curve gate on Sharpe AND MaxDD AND beats 200dma AND holds
leave-one-crisis-out (no single crisis carries the edge). Else CONFIRMER (tail
insurance / gives up CAGR / honest-N too small). Display if nothing.

Run: ./.venv/bin/python3 scripts/intl_macro_sleeve_phase0.py
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
    block_bootstrap_ci, _sharpe, _maxdd,
)

ROOT = Path(__file__).resolve().parent.parent
INTL = ROOT / "data" / "intl"
MACRO = ROOT / "data" / "intl_macro"
ANN = 252
COST_BPS = 3.0           # one-way; macro gate trades a handful of times/yr
PUB_LAG_M = 1            # publication lag (months) applied to ALL monthly macro

# market -> (price index file, country macro prefix, fallback price file)
MARKETS = {
    "JP": {"px": "_N225", "fallback": None},
    "EZ": {"px": "_STOXX50E", "fallback": "_GDAXI"},   # STOXX50E only from 2007; GDAXI from 1988
    "GB": {"px": "_FTSE", "fallback": None},
    "KR": {"px": "_KS11", "fallback": None},
}

# Independent crisis windows per market (for leave-one-crisis-out). HONEST-N.
CRISES = {
    "JP": {"dotcom_00": ("2000-03", "2003-04"), "gfc_08": ("2007-07", "2009-03"),
           "covid_20": ("2020-01", "2020-04"), "rate_22": ("2022-01", "2022-12")},
    "EZ": {"gfc_08": ("2007-07", "2009-03"), "eurozone_11": ("2011-05", "2012-07"),
           "covid_20": ("2020-01", "2020-04"), "rate_22": ("2022-01", "2022-12")},
    "GB": {"dotcom_00": ("2000-03", "2003-04"), "gfc_08": ("2007-07", "2009-03"),
           "covid_20": ("2020-01", "2020-04"), "rate_22": ("2022-01", "2022-12")},
    "KR": {"dotcom_00": ("2000-03", "2003-04"), "gfc_08": ("2007-07", "2009-03"),
           "covid_20": ("2020-01", "2020-04"), "rate_22": ("2022-01", "2022-12")},
}


# --------------------------------------------------------------------------- #
# data loaders
# --------------------------------------------------------------------------- #
def load_px(name: str) -> pd.Series:
    df = pd.read_parquet(INTL / f"{name}.parquet")
    s = df["close"].copy()
    s.index = pd.to_datetime(s.index)
    return s[~s.index.duplicated(keep="last")].sort_index().dropna()


def load_macro(country: str, metric: str) -> pd.Series | None:
    f = MACRO / f"{country}_{metric}.parquet"
    if not f.exists():
        return None
    df = pd.read_parquet(f)
    s = df.iloc[:, 0].copy()
    s.index = pd.to_datetime(s.index)
    s = s[~s.index.duplicated(keep="last")].sort_index().dropna()
    # apply publication lag (shift the dated value forward PUB_LAG_M months)
    s.index = s.index + pd.DateOffset(months=PUB_LAG_M)
    return s


def to_daily(s: pd.Series | None, idx: pd.DatetimeIndex) -> pd.Series:
    """Forward-fill a (lagged) monthly series onto the daily price index. No look-ahead:
    a value dated month M (already +1m lagged) is only visible from M onward."""
    if s is None or s.empty:
        return pd.Series(np.nan, index=idx)
    return s.reindex(idx.union(s.index)).ffill().reindex(idx)


# --------------------------------------------------------------------------- #
# the lean macro de-risk gate
# --------------------------------------------------------------------------- #
def build_gate(country: str, idx: pd.DatetimeIndex) -> dict:
    """Returns dict with daily-aligned leg booleans + the composite alloc.
    All legs computed on the MONTHLY (lagged) frequency then ffilled to daily."""
    y10 = load_macro(country, "yield_10y")
    s3m = load_macro(country, "short_3m")
    unemp = load_macro(country, "unemployment")

    # --- leg 1: curve inversion (monthly) ---
    curve_inv = None
    if y10 is not None and s3m is not None:
        spread = (y10 - s3m.reindex(y10.index).interpolate(limit_area="inside"))
        curve_inv = (spread < 0.0)
    # --- leg 2: Sahm-style unemployment rise (monthly) ---
    sahm = None
    if unemp is not None:
        u3 = unemp.rolling(3, min_periods=2).mean()
        u_min12 = unemp.rolling(12, min_periods=6).min()
        sahm = ((u3 - u_min12) >= 0.5)
    # --- leg 3: short-rate tightening (monthly) ---
    short_tight = None
    if s3m is not None:
        chg3 = s3m.diff(3)
        mean12 = s3m.rolling(12, min_periods=6).mean()
        short_tight = ((chg3 > 0.0) & (s3m > mean12))

    legs_daily = {}
    for nm, leg in (("curve", curve_inv), ("sahm", sahm), ("short", short_tight)):
        legs_daily[nm] = to_daily(leg.astype(float) if leg is not None else None, idx).fillna(0.0)

    n_legs = legs_daily["curve"] + legs_daily["sahm"] + legs_daily["short"]
    # composite: glide to bills as legs fire (half at >=1, flat at >=2)
    alloc = pd.Series(1.0, index=idx)
    alloc = alloc.where(n_legs < 1, 0.5)
    alloc = alloc.where(n_legs < 2, 0.0)

    cash = to_daily(s3m, idx)            # local short rate as the bill yield (annualized %)
    return {"alloc": alloc, "cash": cash, "legs": legs_daily, "n_legs": n_legs,
            "have": {k: (legs_daily[k].abs().sum() > 0) for k in legs_daily}}


def dumb_curve_gate(country: str, idx: pd.DatetimeIndex) -> tuple[pd.Series, pd.Series]:
    """The DUMB single-leg baseline: flat WHENEVER the curve is inverted. (We must beat this.)"""
    y10 = load_macro(country, "yield_10y")
    s3m = load_macro(country, "short_3m")
    cash = to_daily(s3m, idx)
    if y10 is None or s3m is None:
        return pd.Series(1.0, index=idx), cash
    spread = (y10 - s3m.reindex(y10.index).interpolate(limit_area="inside"))
    inv = to_daily((spread < 0.0).astype(float), idx).fillna(0.0)
    return pd.Series(1.0, index=idx).where(inv < 1, 0.0), cash


# --------------------------------------------------------------------------- #
# scoring
# --------------------------------------------------------------------------- #
def metrics(net: pd.Series) -> dict:
    r = net.dropna()
    if len(r) < 120:
        return {"n": len(r)}
    eq = (1.0 + r).cumprod()
    return {"cagr": (eq.iloc[-1] ** (ANN / len(r)) - 1.0) * 100,
            "sharpe": _sharpe(r.to_numpy(), ANN), "maxdd": _maxdd(r.to_numpy()) * 100,
            "n": len(r)}


def fmt(label, m, w=24) -> str:
    if m.get("n", 0) < 120:
        return f"  {label:<{w}} (insufficient n={m.get('n',0)})"
    return (f"  {label:<{w}} CAGR={m['cagr']:+6.2f}%  Sharpe={m['sharpe']:+5.2f}  "
            f"MaxDD={m['maxdd']:+7.1f}%  n={m['n']}")


def run_market(country: str, lines: list) -> dict:
    spec = MARKETS[country]
    px = load_px(spec["px"])
    if spec["fallback"]:                 # prefer the longer history for the gate test
        fb = load_px(spec["fallback"])
        if len(fb) > len(px) * 1.3:
            px = fb
            usedpx = f"{spec['fallback']} (fallback, longer)"
        else:
            usedpx = spec["px"]
    else:
        usedpx = spec["px"]

    idx = px.index
    g = build_gate(country, idx)
    alloc, cash = g["alloc"], g["cash"]

    # honest common window: only where the gate has data (cash present) AND price
    start = max(px.index[0], (cash.dropna().index[0] if cash.notna().any() else px.index[0]))
    sl = slice(start, px.index[-1])

    bh_net = backtest_core(px, pd.Series(1.0, index=idx), cost_bps=0.0, cash_yield=None)["net"].loc[sl]
    dma = (px > px.rolling(200, min_periods=120).mean()).astype(float)
    dma_net = backtest_core(px, dma, cost_bps=COST_BPS, cash_yield=cash)["net"].loc[sl]
    dumb_a, dumb_cash = dumb_curve_gate(country, idx)
    dumb_net = backtest_core(px, dumb_a, cost_bps=COST_BPS, cash_yield=dumb_cash)["net"].loc[sl]
    comp_net = backtest_core(px, alloc, cost_bps=COST_BPS, cash_yield=cash)["net"].loc[sl]

    m_bh, m_dma, m_dumb, m_comp = (metrics(bh_net), metrics(dma_net),
                                   metrics(dumb_net), metrics(comp_net))

    lines.append("")
    lines.append("=" * 100)
    lines.append(f"[{country}]  px={usedpx}  window={pd.Timestamp(start).date()} -> {px.index[-1].date()}  "
                 f"legs_have={{c:{int(g['have']['curve'])} s:{int(g['have']['sahm'])} sh:{int(g['have']['short'])}}}")
    lines.append("=" * 100)
    lines.append(fmt("buy & hold (no cash)", m_bh))
    lines.append(fmt("200dma long/flat", m_dma))
    lines.append(fmt("DUMB curve-inv gate", m_dumb))
    lines.append(fmt("MACRO composite", m_comp))
    tim = (alloc.loc[sl] < 0.99).mean() * 100
    lines.append(f"  composite de-risked time-in-flat ~ {tim:.1f}% of days")

    # ---- gate evaluations on the composite ----
    out = {"country": country, "px": usedpx, "m_comp": m_comp, "m_bh": m_bh,
           "m_dma": m_dma, "m_dumb": m_dumb, "net": comp_net,
           "dma_net": dma_net, "dumb_net": dumb_net, "have": g["have"]}

    if m_comp.get("n", 0) < 120:
        out["verdict"] = "display (insufficient data)"
        lines.append("  -> INSUFFICIENT DATA")
        return out

    # split-half same-sign Sharpe
    n = len(comp_net)
    s1 = _sharpe(comp_net.iloc[:n // 2].dropna().to_numpy(), ANN)
    s2 = _sharpe(comp_net.iloc[n // 2:].dropna().to_numpy(), ANN)
    same_sign = np.sign(s1) == np.sign(s2) and np.isfinite(s1) and np.isfinite(s2)
    lines.append(f"  split-half Sharpe {s1:+.2f} / {s2:+.2f}  same-sign={'YES' if same_sign else 'NO'}")

    # beat baselines? (edge defined as Sharpe up AND MaxDD shallower than each baseline)
    def beats(b):
        return (m_comp["sharpe"] >= b["sharpe"] - 1e-9) and (m_comp["maxdd"] >= b["maxdd"] - 1e-9)
    beats_dumb = beats(m_dumb)
    beats_dma = beats(m_dma)
    beats_bh_dd = m_comp["maxdd"] >= m_bh["maxdd"] - 1e-9   # tail-insurance read: shallower DD than B&H
    lines.append(f"  beats DUMB curve gate (Sharpe&DD)={beats_dumb}   beats 200dma={beats_dma}   "
                 f"shallower-DD-than-B&H={beats_bh_dd}")

    # leave-one-crisis-out: re-score composite Sharpe with each crisis window EXCISED
    loco_ok = True
    loco_detail = []
    base_sh = m_comp["sharpe"]
    for cname, (c0, c1) in CRISES[country].items():
        mask = ~((comp_net.index >= pd.Timestamp(c0)) & (comp_net.index <= pd.Timestamp(c1)))
        r = comp_net[mask].dropna()
        bh_r = bh_net[mask].dropna()
        if len(r) < 120:
            continue
        sh = _sharpe(r.to_numpy(), ANN)
        sh_bh = _sharpe(bh_r.to_numpy(), ANN)
        dd = _maxdd(r.to_numpy()) * 100
        dd_bh = _maxdd(bh_r.to_numpy()) * 100
        # the edge must persist: shallower DD than B&H even with this crisis removed
        ok = dd >= dd_bh - 1e-9
        loco_ok &= ok
        loco_detail.append((cname, sh, dd, dd_bh, ok))
    lines.append("  leave-one-crisis-out (composite vs B&H, DD-edge must persist):")
    for cname, sh, dd, dd_bh, ok in loco_detail:
        lines.append(f"    drop {cname:<12} compSharpe={sh:+5.2f}  compDD={dd:+6.1f}%  "
                     f"bhDD={dd_bh:+6.1f}%  edge-holds={ok}")

    # honest-N: count independent crises actually inside the sample
    n_crises = sum(1 for _c, (c0, _c1) in CRISES[country].items()
                   if pd.Timestamp(c0) >= pd.Timestamp(start))
    out.update({"s1": s1, "s2": s2, "same_sign": same_sign, "beats_dumb": beats_dumb,
                "beats_dma": beats_dma, "beats_bh_dd": beats_bh_dd, "loco_ok": loco_ok,
                "n_crises": n_crises})
    return out


def main() -> None:
    lines = []
    lines.append("#" * 100)
    lines.append("INTERNATIONAL MACRO-TIMED EQUITY SLEEVES (JP/EZ/GB/KR) — Phase-0")
    lines.append(f"  port of S&P/Macro Vector (long/flat equity-vs-bills, scored on Sharpe+MaxDD reduction)")
    lines.append(f"  macro lag = +{PUB_LAG_M}m publication; cost = {COST_BPS}bps one-way; cash = local short_3m")
    lines.append("#" * 100)

    results = {}
    for c in MARKETS:
        results[c] = run_market(c, lines)

    # n_trials for the DSR: markets (4) x gate variants tried (composite + dumb-curve
    # + 200dma proxy = ~3 per market). HONEST upward bias of picking the best.
    n_variants_per_mkt = 3
    n_trials = len(MARKETS) * n_variants_per_mkt

    lines.append("")
    lines.append("=" * 100)
    lines.append(f"### DEFLATED SHARPE (per market) — n_trials = {len(MARKETS)} markets x {n_variants_per_mkt} variants = {n_trials}")
    lines.append("=" * 100)
    for c in MARKETS:
        r = results[c]
        if "net" not in r or r["m_comp"].get("n", 0) < 120:
            lines.append(f"  [{c}] (insufficient)")
            continue
        mom = ret_moments(r["net"])
        if not mom:
            lines.append(f"  [{c}] (no moments)")
            continue
        sr, sk, ku, nn = mom
        d = deflated_sharpe(sr, sk, ku, nn, n_trials=n_trials, trading_year=ANN)
        r["dsr"] = d["dsr"]
        lines.append(f"  [{c}] DSR={d['dsr']:.4f} ({dsr_verdict(d['dsr'])})  "
                     f"SR_ann={d['sr_annual']:+.2f}  SR0_ann={d['sr0_annual']:+.2f}")

    # ---------- POOLED: equal-risk Intl Macro Vector ----------
    lines.append("")
    lines.append("=" * 100)
    lines.append("### POOLED 'Intl Macro Vector' — equal-RISK (inverse-vol) across the 4 markets")
    lines.append("=" * 100)
    # align each market's composite net AND its B&H net on a common daily index
    comp_nets, bh_nets = {}, {}
    for c in MARKETS:
        r = results[c]
        if "net" in r and r["m_comp"].get("n", 0) >= 120:
            comp_nets[c] = r["net"]
    common = None
    for c, s in comp_nets.items():
        common = s.index if common is None else common.union(s.index)
    # equal-risk: weight each market by inverse trailing-63d vol, renormalized daily,
    # computed CAUSALLY (vol through t-1).
    comp_df = pd.DataFrame({c: s.reindex(common) for c, s in comp_nets.items()})
    # rebuild each market's B&H on the common index for the pooled benchmark
    for c in MARKETS:
        spec = MARKETS[c]
        px = load_px(spec["px"])
        if spec["fallback"]:
            fb = load_px(spec["fallback"])
            if len(fb) > len(px) * 1.3:
                px = fb
        bh = px.pct_change()
        bh_nets[c] = bh.reindex(common)
    bh_df = pd.DataFrame({c: bh_nets[c] for c in comp_nets})

    # pool the per-market DUMB baselines too, on the SAME inverse-vol weights, so the
    # pooled macro sleeve is held to the SAME bar as each market (beat 200dma + dumb curve).
    dma_df = pd.DataFrame({c: results[c]["dma_net"].reindex(common) for c in comp_nets})
    dumb_df = pd.DataFrame({c: results[c]["dumb_net"].reindex(common) for c in comp_nets})

    def eq_risk(df_ret: pd.DataFrame, idx) -> pd.Series:
        v = df_ret.rolling(63, min_periods=21).std().shift(1)
        ivv = (1.0 / v).replace([np.inf, -np.inf], np.nan)
        ww = ivv.div(ivv.sum(axis=1), axis=0)
        return (ww * df_ret).sum(axis=1).reindex(idx)

    vol = comp_df.rolling(63, min_periods=21).std().shift(1)
    iv = (1.0 / vol).replace([np.inf, -np.inf], np.nan)
    w = iv.div(iv.sum(axis=1), axis=0)
    pooled = (w * comp_df).sum(axis=1)
    pooled = pooled[w.notna().any(axis=1)].dropna()
    # equal-risk B&H benchmark, same weights logic on B&H vol
    pooled_bh = eq_risk(bh_df, pooled.index).dropna()
    pooled = pooled.reindex(pooled_bh.index)
    pooled_dma = eq_risk(dma_df, pooled.index)
    pooled_dumb = eq_risk(dumb_df, pooled.index)

    m_pool = metrics(pooled)
    m_pool_bh = metrics(pooled_bh)
    m_pool_dma = metrics(pooled_dma)
    m_pool_dumb = metrics(pooled_dumb)
    lines.append(fmt("pooled B&H (eq-risk)", m_pool_bh))
    lines.append(fmt("pooled 200dma (eq-risk)", m_pool_dma))
    lines.append(fmt("pooled DUMB curve (eq-risk)", m_pool_dumb))
    lines.append(fmt("pooled MACRO (eq-risk)", m_pool))
    pool_out = {"m_comp": m_pool, "m_bh": m_pool_bh, "m_dma": m_pool_dma, "m_dumb": m_pool_dumb}
    if m_pool.get("n", 0) >= 120:
        np_ = len(pooled)
        ps1 = _sharpe(pooled.iloc[:np_ // 2].dropna().to_numpy(), ANN)
        ps2 = _sharpe(pooled.iloc[np_ // 2:].dropna().to_numpy(), ANN)
        pss = np.sign(ps1) == np.sign(ps2)
        lines.append(f"  pooled split-half Sharpe {ps1:+.2f} / {ps2:+.2f}  same-sign={'YES' if pss else 'NO'}")
        mom = ret_moments(pooled)
        if mom:
            sr, sk, ku, nn = mom
            d = deflated_sharpe(sr, sk, ku, nn, n_trials=n_trials + 1, trading_year=ANN)
            lines.append(f"  pooled DSR={d['dsr']:.4f} ({dsr_verdict(d['dsr'])})  SR_ann={d['sr_annual']:+.2f}")
            ci = block_bootstrap_ci(pooled, block=21, B=3000, ann=ANN)
            if ci:
                lines.append(f"  pooled Sharpe 95% CI {ci['sharpe_ci']}  MaxDD 95% CI {ci['maxdd_ci_pct']}%")
            pool_out.update({"dsr": d["dsr"], "s1": ps1, "s2": ps2, "same_sign": pss})

            def beats_pool(b):
                return (m_pool["sharpe"] >= b["sharpe"] - 1e-9) and (m_pool["maxdd"] >= b["maxdd"] - 1e-9)
            beats_dd = m_pool["maxdd"] >= m_pool_bh["maxdd"] - 1e-9
            pool_out["beats_bh_dd"] = beats_dd
            pool_out["beats_dma"] = beats_pool(m_pool_dma)
            pool_out["beats_dumb"] = beats_pool(m_pool_dumb)
            lines.append(f"  pooled shallower-DD-than-eqrisk-B&H = {beats_dd}   "
                         f"beats 200dma (Sharpe&DD)={pool_out['beats_dma']}   "
                         f"beats DUMB curve={pool_out['beats_dumb']}")

    # ---------- VERDICTS ----------
    lines.append("")
    lines.append("=" * 100)
    lines.append("### VERDICTS (scored requires: DSR>=0.90 AND same-sign split-half AND beats DUMB curve")
    lines.append("###   AND beats 200dma AND leave-one-crisis-out holds AND honest-N >= 3 crises)")
    lines.append("=" * 100)
    verdicts = {}
    for c in MARKETS:
        r = results[c]
        if r.get("m_comp", {}).get("n", 0) < 120:
            verdicts[c] = "display"
            lines.append(f"  [{c}] DISPLAY — insufficient data")
            continue
        dsr = r.get("dsr", 0.0)
        cond = {
            "DSR>=0.90": dsr >= 0.90,
            "same-sign split": r.get("same_sign", False),
            "beats DUMB curve": r.get("beats_dumb", False),
            "beats 200dma": r.get("beats_dma", False),
            "LOCO holds": r.get("loco_ok", False),
            "honest-N>=3": r.get("n_crises", 0) >= 3,
        }
        scored = all(cond.values())
        # confirmer = provides DD insurance vs B&H even if not a scored timer
        confirmer = r.get("beats_bh_dd", False) and r.get("same_sign", False)
        v = "SCORED" if scored else ("CONFIRMER" if confirmer else "DISPLAY")
        verdicts[c] = v
        lines.append(f"  [{c}] {v}  (DSR={dsr:.3f})")
        for k, ok in cond.items():
            lines.append(f"        {'PASS' if ok else 'FAIL'}  {k}")

    # pooled verdict — held to the SAME bar as per-market (beat dumb curve AND 200dma)
    pdsr = pool_out.get("dsr", 0.0)
    pcond = {"DSR>=0.90": pdsr >= 0.90, "same-sign split": pool_out.get("same_sign", False),
             "beats DUMB curve": pool_out.get("beats_dumb", False),
             "beats 200dma": pool_out.get("beats_dma", False),
             "shallower-DD-than-B&H": pool_out.get("beats_bh_dd", False)}
    pscored = all(pcond.values())
    pconfirmer = pool_out.get("beats_bh_dd", False) and pool_out.get("same_sign", False)
    pv = "SCORED" if pscored else ("CONFIRMER" if pconfirmer else "DISPLAY")
    verdicts["POOLED"] = pv
    lines.append(f"  [POOLED] {pv}  (DSR={pdsr:.3f})")
    for k, ok in pcond.items():
        lines.append(f"        {'PASS' if ok else 'FAIL'}  {k}")

    lines.append("")
    lines.append("=" * 100)
    lines.append("READ-ME: a macro-timer SCORES only as a Sharpe+MaxDD-reduction tail-insurance sleeve that")
    lines.append("  survives the multiple-testing haircut AND adds over the dumb curve-inversion gate AND")
    lines.append("  does not hinge on a single crisis. With ~3-5 independent bears/market, honest-N is the")
    lines.append("  binding constraint — most ports land CONFIRMER (real DD relief, but the edge is fragile).")
    lines.append("=" * 100)

    report = "\n".join(lines)
    print(report)
    out_path = ROOT / "reports" / "intl-macro-sleeve-phase0.md"
    out_path.write_text("```\n" + report + "\n```\n", encoding="utf-8")
    print(f"\n[written] {out_path}")
    # stash verdicts for the caller's convenience
    return verdicts


if __name__ == "__main__":
    main()
