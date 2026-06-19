"""Phase-0 honest validation — Intl TOTAL-RETURN tradeable trend / macro-gated overlay.

READ-ONLY research harness (prints + writes reports/intl-tr-trend-phase0.md).

THE DATA-UNBLOCK
----------------
The prior `intl_trend_overlay_phase0.py` landed CONFIRMER and one suspected reason
was that `data/intl/*.parquet` are PRICE-only LOCAL-currency indices (no dividends,
not directly tradeable). Here we COLLECT total-return, USD-denominated, *tradeable*
country ETFs via yfinance (auto_adjust=True == dividend-adjusted close):

    EWJ(JP)  EWG(DE)  EWU(UK)  EWY(KR)  EWA(AU)  EWQ(FR)

written to data/intl/_etf_scratch/<TICKER>.parquet (scratch; NOT assumed committed).
These are what a US investor actually trades: USD total return = local price +
dividends + FX. The flat sleeve is credited with the US 3m T-bill (the cash a US
holder earns when de-risked), so cost+carry are paid HONESTLY against an
all-equity buy&hold of the same ETF.

THE QUESTION
------------
Does total-return + tradeability change the verdict vs the price-index version
(which gave up CAGR and FAILED split-half on Sharpe)? Honest prior: total-return
likely makes TREND WORSE — dividends + the secular USD-equity drift cushion the
very downside the local price-index trend exploited (N225 in JPY lost 80% over
two decades; EWJ in USD did not).

TWO TRACKS (per spec):
  (a) 200d SMA + 12-1m TSMOM trend de-risk long/flat overlay.
  (b) macro-gated long/flat: a DUMB recession/curve-inversion gate built from the
      local macro series (10y-3m curve inversion OR rising-unemployment Sahm-ish),
      for the 4 ETFs that have a local macro panel (EWJ=JP, EWG/EWQ=EZ, EWU=GB,
      EWY=KR). No look-ahead: monthly macro is ffilled, the signal at t acts t+1.

SCORED bar (every gate must clear), per spec:
  - DSR>=0.90 ('survives'>=0.95) on the POOLED book AND per-ETF, n_trials honest.
  - drawdown-reduction block-bootstrap CI excludes 0.
  - same-sign split-half (Sharpe edge holds in BOTH halves).
  - leave-one-crisis-out {2008,2011,2020,2022} holds.
  - beats LOCAL buy&hold AND a flat-60/40 baseline (risk-adjusted; the de-risk
    pitch is Sharpe+MaxDD, NOT CAGR), net 5-10 bps.
  - honest-N: count INDEPENDENT crises, not raw rows.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.validation import (  # noqa: E402
    backtest_core, ret_moments, deflated_sharpe, dsr_verdict,
    _maxdd, _sharpe,
)
from engine.active_alloc import backtest_portfolio, split_half_oos  # noqa: E402

SCRATCH = ROOT / "data" / "intl" / "_etf_scratch"
MACRO = ROOT / "data" / "intl_macro"
FRED = ROOT / "data" / "fred"

# ETF -> (local macro country-prefix or None). FR maps to EZ (euro-area macro).
ETFS = {
    "EWJ": "JP",   # Japan
    "EWG": "EZ",   # Germany -> euro-area macro
    "EWU": "GB",   # UK
    "EWY": "KR",   # Korea
    "EWA": None,   # Australia -- NO local macro panel -> trend-only
    "EWQ": "EZ",   # France -> euro-area macro
}

# Independent crisis eras (honest-N). The spec's required LOCO set is the global
# 4 {2008,2011,2020,2022}; we also carry Dotcom for the ETFs that span it.
CRISES = {
    "Dotcom":   ("2000-03-01", "2002-12-31"),
    "GFC":      ("2007-10-01", "2009-06-30"),
    "EuroDebt": ("2011-05-01", "2011-12-31"),   # 2011
    "COVID":    ("2020-02-01", "2020-05-31"),
    "Bear2022": ("2022-01-01", "2022-12-31"),
}
# spec-mandated LOCO set:
LOCO_CRISES = ["GFC", "EuroDebt", "COVID", "Bear2022"]

COST_BPS = 7.0          # one-way; liquid ETFs, spec says 5-10 -> midpoint 7
TRADING_YEAR = 252


# --------------------------------------------------------------------------- #
# data
# --------------------------------------------------------------------------- #
def load_close(ticker: str) -> pd.Series:
    df = pd.read_parquet(SCRATCH / f"{ticker}.parquet")
    s = df["close"].dropna()
    s.index = pd.to_datetime(s.index)
    return s[~s.index.duplicated(keep="last")].sort_index()


def us_bill(idx: pd.DatetimeIndex) -> pd.Series:
    """US 3m T-bill (%) aligned to idx, ffilled. USD ETFs -> a US holder's de-risk
    sleeve earns the US bill, not a local one. This is the HONEST carry credit."""
    r = pd.read_parquet(FRED / "DGS3MO.parquet").iloc[:, 0].dropna()
    r.index = pd.to_datetime(r.index)
    r = r.reindex(idx, method="ffill").clip(lower=0.0)
    # pre-1982 DGS3MO doesn't exist but ETFs start 1996, so this is always covered.
    return r.fillna(0.0)


def load_macro(prefix: str) -> dict:
    """Local macro frame for the curve/unemployment gate. Returns dict of monthly
    Series (10y, 3m, unemployment) — whichever exist."""
    out = {}
    for key, fname in (("y10", f"{prefix}_yield_10y"),
                       ("s3m", f"{prefix}_short_3m"),
                       ("unemp", f"{prefix}_unemployment")):
        fp = MACRO / f"{fname}.parquet"
        if fp.exists():
            s = pd.read_parquet(fp).iloc[:, 0].dropna()
            s.index = pd.to_datetime(s.index)
            out[key] = s.sort_index()
    return out


# --------------------------------------------------------------------------- #
# signals (decision AS OF t; backtest_core lags to t+1)
# --------------------------------------------------------------------------- #
def sig_sma200(close: pd.Series) -> pd.Series:
    sma = close.rolling(200, min_periods=200).mean()
    return (close > sma).astype(float).where(sma.notna(), np.nan)


def sig_tsmom(close: pd.Series) -> pd.Series:
    """12-1 month TSMOM: long if trailing 12m return (skip last 1m) > 0."""
    mom = close.shift(21) / close.shift(252) - 1.0
    sig = (mom > 0).astype(float)
    sig[close.shift(252).isna()] = np.nan
    return sig


def sig_macro(close: pd.Series, prefix: str | None) -> pd.Series | None:
    """DUMB recession/curve gate (long/flat). FLAT (de-risk) when EITHER
      - the 10y-3m curve is inverted (level < 0), OR
      - unemployment is rising (12m change > 0 AND latest > its 12m min by >= 0.3pp,
        a coarse Sahm-ish 'labor turning' flag),
    else LONG. Monthly macro ffilled to daily; decision AS OF t (acts t+1).
    NO look-ahead: only data dated <= t is used (ffill of monthly releases; we DO
    NOT pretend month-end data is known intra-month -- ffill carries the LAST
    published value, which is the conservative live behavior)."""
    if prefix is None:
        return None
    m = load_macro(prefix)
    if "y10" not in m or "s3m" not in m:
        return None
    idx = close.index
    y10 = m["y10"].reindex(idx, method="ffill")
    s3m = m["s3m"].reindex(idx, method="ffill")
    curve = y10 - s3m
    inverted = curve < 0.0

    if "unemp" in m:
        u = m["unemp"].reindex(idx, method="ffill")
        u12 = u.shift(252)
        umin12 = u.rolling(252, min_periods=60).min()
        labor_turning = (u - u12 > 0.0) & (u - umin12 >= 0.3)
        labor_turning = labor_turning.fillna(False)
    else:
        labor_turning = pd.Series(False, index=idx)

    de_risk = inverted.fillna(False) | labor_turning
    sig = (~de_risk).astype(float)
    # warm-up: undefined until both curve legs exist
    sig[y10.isna() | s3m.isna()] = np.nan
    return sig


TREND_VARIANTS = {"sma200": sig_sma200, "tsmom": sig_tsmom}


# --------------------------------------------------------------------------- #
# per-ETF single-asset backtest (trend variant)
# --------------------------------------------------------------------------- #
def run_one(ticker: str, alloc_fn, prefix=None, is_macro=False):
    close = load_close(ticker)
    cy = us_bill(close.index)
    if is_macro:
        alloc = sig_macro(close, prefix)
        if alloc is None:
            return None
    else:
        alloc = alloc_fn(close)
    valid = alloc.dropna().index
    if len(valid) < 252:
        return None
    bt = backtest_core(close, alloc, cost_bps=COST_BPS, cash_yield=cy)
    start = valid[0]
    net = bt["net"].loc[start:]
    hold = bt["hold"].loc[start:]
    pos = bt["pos"].loc[start:]
    eq = (1 + net).cumprod()
    heq = (1 + hold).cumprod()
    years = (net.index[-1] - net.index[0]).days / 365.25
    return {
        "ticker": ticker, "close": close, "cy": cy, "alloc": alloc.reindex(close.index),
        "net": net, "hold": hold, "pos": pos, "eq": eq, "heq": heq, "years": years,
        "sharpe": _sharpe(net.values, TRADING_YEAR),
        "hold_sharpe": _sharpe(hold.values, TRADING_YEAR),
        "maxdd": _maxdd(net.values) * 100,
        "hold_maxdd": _maxdd(hold.values) * 100,
        "cagr": cagr(eq, years), "hold_cagr": cagr(heq, years),
        "time_in": float((pos > 1e-6).mean()) * 100,
    }


def cagr(eq: pd.Series, years: float) -> float:
    if years <= 0 or eq.iloc[-1] <= 0:
        return np.nan
    return (eq.iloc[-1] ** (1 / years) - 1) * 100


# --------------------------------------------------------------------------- #
# paired block-bootstrap of MaxDD-reduction (pp), trend vs buy&hold
# --------------------------------------------------------------------------- #
def ddreduction_ci(trend: pd.Series, bh: pd.Series, block: int = 63,
                   B: int = 4000, seed: int = 7) -> dict:
    j = pd.concat([trend.rename("t"), bh.rename("b")], axis=1).dropna()
    if len(j) < max(block * 3, 200):
        return {}
    t = j["t"].to_numpy(); b = j["b"].to_numpy(); n = len(t)
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(n / block)); grid = np.arange(block)
    red = np.empty(B)
    for k in range(B):
        starts = rng.integers(0, n, nb)
        idx = (starts[:, None] + grid[None, :]).ravel()[:n] % n
        red[k] = (_maxdd(t[idx]) - _maxdd(b[idx])) * 100.0   # trendDD - bhDD; >0 = trend shallower
    return {"ci": [round(float(np.percentile(red, p)), 1) for p in (2.5, 50, 97.5)],
            "prob_gt0": round(float(np.mean(red > 0)), 3), "n": n, "B": B, "block": block}


# --------------------------------------------------------------------------- #
# pooled EW book builder
# --------------------------------------------------------------------------- #
def build_pooled(members, alloc_map, cost_bps=COST_BPS):
    """EW book: 1/N per member when its signal is long, else cash (US bill).
    Returns (trend_net, bh_net, flat_net, scorecard). Starts at the latest
    first-valid signal across members so every leg is warmed up."""
    closes = pd.DataFrame({m: load_close(m) for m in members}).sort_index()
    idx = closes.index
    bill = us_bill(idx)
    W = pd.DataFrame(index=idx)
    starts = []
    for m in members:
        a = alloc_map[m].reindex(idx)
        W[m] = a / len(members)
        av = a.dropna()
        if len(av):
            starts.append(av.index[0])
    W = W.fillna(0.0)
    start = max(starts) if starts else idx[0]
    Wc = W.loc[start:]; closes_c = closes.loc[start:]; bill_c = bill.loc[start:]

    bk = backtest_portfolio(Wc, closes_c, bill_c, cost_bps=cost_bps, borrow_spread=1.0)
    net = bk["net"].dropna()

    Whold = pd.DataFrame(1.0 / len(members), index=closes_c.index, columns=members)
    bh = backtest_portfolio(Whold, closes_c, bill_c, cost_bps=0.0, borrow_spread=1.0)
    bh_net = bh["net"].dropna()

    Wflat = pd.DataFrame(0.6 / len(members), index=closes_c.index, columns=members)
    flat = backtest_portfolio(Wflat, closes_c, bill_c, cost_bps=0.0, borrow_spread=1.0)
    flat_net = flat["net"].dropna()

    return {"net": net, "bh_net": bh_net, "flat_net": flat_net, "bk": bk,
            "start": start, "members": members, "closes": closes_c}


# --------------------------------------------------------------------------- #
def main():
    out = []
    def p(*a):
        line = " ".join(str(x) for x in a); print(line); out.append(line)

    p("=" * 80)
    p("PHASE-0: Intl TOTAL-RETURN tradeable trend / macro-gated overlay")
    p("=" * 80)
    p(f"data = data/intl/_etf_scratch/<TICKER>.parquet (yfinance auto_adjust=True, USD TR)")
    p(f"cost_bps(one-way)={COST_BPS}  cash=US 3m T-bill (DGS3MO) on the flat sleeve")
    p(f"trend variants={list(TREND_VARIANTS)}  macro-gate on {[k for k,v in ETFS.items() if v]}")
    p(f"ETFs={list(ETFS)}")
    p("")

    # ---------------------------------------------------------------- #
    # PER-ETF table: trend (sma200 + tsmom) + macro-gate
    # ---------------------------------------------------------------- #
    runs = {}   # (ticker, label) -> run
    p(f"{'etf':5} {'signal':9} {'yrs':>5} {'netSh':>7} {'holdSh':>7} "
      f"{'netDD%':>7} {'holdDD%':>8} {'ddCut':>7} {'netCAGR':>8} {'hCAGR':>7} {'tIn%':>6}")
    p("-" * 80)
    for tk, prefix in ETFS.items():
        for v, fn in TREND_VARIANTS.items():
            r = run_one(tk, fn)
            if r is None:
                continue
            runs[(tk, v)] = r
            ddcut = r["hold_maxdd"] - r["maxdd"]
            p(f"{tk:5} {v:9} {r['years']:5.1f} {r['sharpe']:7.3f} {r['hold_sharpe']:7.3f} "
              f"{r['maxdd']:7.1f} {r['hold_maxdd']:8.1f} {ddcut:7.1f} "
              f"{r['cagr']:8.2f} {r['hold_cagr']:7.2f} {r['time_in']:6.1f}")
        # macro gate
        if prefix is not None:
            rm = run_one(tk, None, prefix=prefix, is_macro=True)
            if rm is not None:
                runs[(tk, "macro")] = rm
                ddcut = rm["hold_maxdd"] - rm["maxdd"]
                p(f"{tk:5} {'macro':9} {rm['years']:5.1f} {rm['sharpe']:7.3f} {rm['hold_sharpe']:7.3f} "
                  f"{rm['maxdd']:7.1f} {rm['hold_maxdd']:8.1f} {ddcut:7.1f} "
                  f"{rm['cagr']:8.2f} {rm['hold_cagr']:7.2f} {rm['time_in']:6.1f}")
    p("")

    n_trials = len(runs)   # every (etf x signal) tried -> honest DSR trial count
    p(f"n_trials (etf x signal, NO cherry-pick) = {n_trials}")
    p("")

    # ---------------------------------------------------------------- #
    # PER-ETF gate check: which single ETF/signal clears the SCORED bar?
    # ---------------------------------------------------------------- #
    p("=" * 80)
    p("PER-ETF / PER-SIGNAL SCORED-BAR CHECK (any single one can score)")
    p("=" * 80)
    per_etf_verdicts = {}
    for (tk, lbl), r in runs.items():
        net = r["net"]; hold = r["hold"]
        mom = ret_moments(net)
        dsr = None
        if mom:
            sr_d, sk, ku, T = mom
            dsr = deflated_sharpe(sr_d, sk, ku, T, n_trials=n_trials, trading_year=TRADING_YEAR)
        dsr_v = dsr["dsr"] if dsr else float("nan")
        # split-half Sharpe edge
        sh = split_half_oos(net, hold)
        ss_sharpe = False; ss_dd = False
        if sh:
            f, s = sh.get("first", {}), sh.get("second", {})
            d1 = (f.get("sharpe", 0) or 0) - (f.get("hodl_sharpe", 0) or 0)
            d2 = (s.get("sharpe", 0) or 0) - (s.get("hodl_sharpe", 0) or 0)
            ss_sharpe = (d1 > 0 and d2 > 0)
            n = len(net)
            dd1 = (_maxdd(net.iloc[:n//2].values) - _maxdd(hold.iloc[:n//2].values)) * 100
            dd2 = (_maxdd(net.iloc[n//2:].values) - _maxdd(hold.iloc[n//2:].values)) * 100
            ss_dd = (dd1 > 0 and dd2 > 0)
        beats_sh = r["sharpe"] > r["hold_sharpe"]
        cuts_dd = r["maxdd"] > r["hold_maxdd"]   # DD negative; closer-to-0 bigger = shallower
        # FULL per-ETF SCORED bar (NOT the loose proxy): DSR>=0.90 AND split-half
        # Sharpe edge same-sign AND beats buy&hold Sharpe AND the single-market
        # DD-reduction bootstrap CI excludes 0 AND the Sharpe edge survives dropping
        # the early/GFC era (post-2010). A scored row on ONE country must be robust.
        ddci = ddreduction_ci(net, hold, block=63, B=4000)
        dd_ci_ok = bool(ddci and ddci["ci"][0] > 0)
        post = net.index >= pd.Timestamp("2010-01-01")
        post_ok = bool(post.sum() > 252 and
                       _sharpe(net[post].values, TRADING_YEAR) >= _sharpe(hold[post].values, TRADING_YEAR))
        scored = bool(dsr and dsr["dsr"] >= 0.90 and ss_sharpe and beats_sh
                      and dd_ci_ok and post_ok)
        per_etf_verdicts[(tk, lbl)] = {
            "dsr": dsr_v, "ss_sharpe": ss_sharpe, "ss_dd": ss_dd,
            "beats_sh": beats_sh, "cuts_dd": cuts_dd,
            "dd_ci_ok": dd_ci_ok, "post_ok": post_ok, "scored": scored,
        }
        p(f"  {tk:4} {lbl:7}: DSR={dsr_v:6.3f} beatsSharpe={int(beats_sh)} cutsDD={int(cuts_dd)} "
          f"sh-half(Sharpe)={int(ss_sharpe)} DD-CI>0={int(dd_ci_ok)} post2010Sh={int(post_ok)} "
          f"-> {'SCORED-candidate' if scored else 'no'}")
    any_etf_scored = any(v["scored"] for v in per_etf_verdicts.values())
    p(f"\n  any single ETF/signal clears the FULL per-ETF SCORED bar? {any_etf_scored}")
    p("  (full bar = DSR>=0.90 AND same-sign split-half Sharpe AND beats buy&hold Sharpe")
    p("   AND single-market DD-reduction CI excludes 0 AND Sharpe edge survives post-2010)")
    p("")

    # ---------------------------------------------------------------- #
    # POOLED EW BASKETS (trend sma200, trend tsmom, macro)
    # ---------------------------------------------------------------- #
    p("=" * 80)
    p("POOLED EQUAL-WEIGHT BASKETS")
    p("=" * 80)
    pooled = {}
    # trend baskets: all 6 ETFs
    for v, fn in TREND_VARIANTS.items():
        members = list(ETFS)
        alloc_map = {m: fn(load_close(m)) for m in members}
        pl = build_pooled(members, alloc_map)
        pooled[("trend", v)] = pl
        _report_pooled(p, f"trend/{v}", pl)
    # macro basket: only the 4 ETFs with a local macro panel
    macro_members = [m for m, pre in ETFS.items() if pre]
    alloc_map = {m: sig_macro(load_close(m), ETFS[m]) for m in macro_members}
    plm = build_pooled(macro_members, alloc_map)
    pooled[("macro", "macro")] = plm
    _report_pooled(p, "macro/curve-gate", plm)

    # ---------------------------------------------------------------- #
    # GATES on the PRIMARY pooled book = trend/sma200 (the headline claim)
    # ---------------------------------------------------------------- #
    p("\n" + "=" * 80)
    p("GATES  (primary = trend/sma200 pooled basket, all 6 ETFs)")
    p("=" * 80)
    prim = pooled[("trend", "sma200")]
    g_primary = run_gates(p, prim, n_trials)

    # also run gates on tsmom + macro pooled (report verdict per archetype)
    p("\n" + "=" * 80)
    p("GATES  (secondary pooled = trend/tsmom)")
    p("=" * 80)
    g_tsmom = run_gates(p, pooled[("trend", "tsmom")], n_trials)

    p("\n" + "=" * 80)
    p("GATES  (secondary pooled = macro/curve-gate, 4 ETFs)")
    p("=" * 80)
    g_macro = run_gates(p, pooled[("macro", "macro")], n_trials)

    # ---------------------------------------------------------------- #
    # VERDICT
    # ---------------------------------------------------------------- #
    p("\n" + "=" * 80)
    p("FINAL VERDICT")
    p("=" * 80)

    def tier_for(name, g):
        all6 = all(g["gates"].values())
        dsr95 = g["dsr"] and g["dsr"]["dsr"] >= 0.95
        if all6 and g["ss_sharpe"] and g["g5_post"] and dsr95:
            t = "SCORED"
        elif g["g2"] and g["g4"]:
            # tail-cut robust but no return edge -> CONFIRMER (de-risk overlay)
            t = "CONFIRMER"
        elif g["g2"]:
            t = "DISPLAY"
        else:
            t = "KILLED"
        p(f"  [{name}] gates={ {k:int(v) for k,v in g['gates'].items()} }")
        p(f"           DSR={g['dsr']['dsr'] if g['dsr'] else None} "
          f"ss_sharpe={int(g['ss_sharpe'])} g5_post={int(g['g5_post'])} -> {t}")
        return t

    t_prim = tier_for("trend/sma200 pooled", g_primary)
    t_tsmom = tier_for("trend/tsmom pooled", g_tsmom)
    t_macro = tier_for("macro/curve pooled", g_macro)

    p("")
    p("  vs PRICE-INDEX version (intl-trend-overlay-phase0): CONFIRMER")
    p("     (tail-cut robust across crises, but Sharpe edge DSR-marginal + not")
    p("      split-half/megabear-robust).")
    p("")
    # overall tier = best of the archetypes (any can score)
    order = {"SCORED": 3, "CONFIRMER": 2, "DISPLAY": 1, "KILLED": 0}
    tiers = {"trend/sma200": t_prim, "trend/tsmom": t_tsmom, "macro/curve": t_macro}
    best = max(tiers.values(), key=lambda x: order[x])
    p(f"  OVERALL (best archetype) = {best}")
    p(f"  per-archetype: {tiers}")
    p(f"  any single ETF scored: {any_etf_scored}")

    rep = ROOT / "reports" / "intl-tr-trend-phase0.md"
    rep.parent.mkdir(exist_ok=True)
    rep.write_text("# Intl TOTAL-RETURN tradeable trend/macro overlay — Phase-0\n\n```\n"
                   + "\n".join(out) + "\n```\n")
    p(f"\nreport -> {rep}")
    return best, tiers, per_etf_verdicts


def _report_pooled(p, label, pl):
    net = pl["net"]; bh = pl["bh_net"]; flat = pl["flat_net"]; bk = pl["bk"]
    yrs = (net.index[-1] - net.index[0]).days / 365.25
    p(f"\n--- {label}  members={pl['members']}  start={pl['start'].date()}  yrs={yrs:.1f}")
    p(f"  STRAT     : Sharpe {bk['sharpe']:.3f}  MaxDD {bk['maxdd']:.1f}%  CAGR {bk['cagr']:.2f}%  finalx {bk['final_mult']:.2f}")
    p(f"  EW buy&hold: Sharpe {_sharpe(bh.values, TRADING_YEAR):.3f}  MaxDD {_maxdd(bh.values)*100:.1f}%  CAGR {cagr((1+bh).cumprod(), yrs):.2f}%")
    p(f"  flat 60/40 : Sharpe {_sharpe(flat.values, TRADING_YEAR):.3f}  MaxDD {_maxdd(flat.values)*100:.1f}%  CAGR {cagr((1+flat).cumprod(), yrs):.2f}%")


def run_gates(p, pl, n_trials):
    net = pl["net"]; bh_net = pl["bh_net"]; flat_net = pl["flat_net"]; bk = pl["bk"]

    # GATE 1: DSR
    mom = ret_moments(net)
    dsr = None
    if mom:
        sr_d, sk, ku, T = mom
        dsr = deflated_sharpe(sr_d, sk, ku, T, n_trials=n_trials, trading_year=TRADING_YEAR)
    p(f"\n[GATE 1] DSR (pooled, n_trials={n_trials})")
    if dsr:
        p(f"  DSR={dsr['dsr']}  SR_ann={dsr['sr_annual']}  SR0_ann={dsr['sr0_annual']}  T={dsr['T']}  -> {dsr_verdict(dsr['dsr'])}")
    g1 = bool(dsr and dsr["dsr"] >= 0.90)

    # GATE 2: DD-reduction block-bootstrap CI excludes 0
    p("\n[GATE 2] Drawdown-reduction block-bootstrap CI (strat vs EW buy&hold)")
    ddred = ddreduction_ci(net, bh_net, block=63, B=4000)
    if ddred:
        p(f"  DD-reduction(pp) CI[2.5/50/97.5]={ddred['ci']}  prob(>0)={ddred['prob_gt0']}  n={ddred['n']}")
    g2 = bool(ddred and ddred["ci"][0] > 0)

    # GATE 3: split-half (Sharpe edge + DD-reduction both halves)
    p("\n[GATE 3] Split-half OOS")
    sh = split_half_oos(net, bh_net)
    ss_sharpe = False; ss_dd = False
    if sh:
        f, s = sh.get("first", {}), sh.get("second", {})
        d1 = (f.get("sharpe", 0) or 0) - (f.get("hodl_sharpe", 0) or 0)
        d2 = (s.get("sharpe", 0) or 0) - (s.get("hodl_sharpe", 0) or 0)
        p(f"  first : strat {f.get('sharpe')}  bh {f.get('hodl_sharpe')}  edge {d1:+.3f}")
        p(f"  second: strat {s.get('sharpe')}  bh {s.get('hodl_sharpe')}  edge {d2:+.3f}")
        n = len(net)
        for lbl, sl in (("first", slice(0, n//2)), ("second", slice(n//2, n))):
            tdd = _maxdd(net.iloc[sl].values) * 100
            hdd = _maxdd(bh_net.iloc[sl].values) * 100
            p(f"  {lbl} MaxDD: strat {tdd:.1f}%  bh {hdd:.1f}%  reduction {tdd-hdd:+.1f}pp")
        ss_sharpe = (d1 > 0 and d2 > 0)
        dd1 = (_maxdd(net.iloc[:n//2].values) - _maxdd(bh_net.iloc[:n//2].values)) * 100
        dd2 = (_maxdd(net.iloc[n//2:].values) - _maxdd(bh_net.iloc[n//2:].values)) * 100
        ss_dd = (dd1 > 0 and dd2 > 0)
        p(f"  same-sign Sharpe-edge both halves: {ss_sharpe}")
        p(f"  same-sign DD-reduction both halves: {ss_dd}")
    g3 = bool(ss_dd)

    # GATE 4: leave-one-crisis-out (within-window tail cut + global LOCO)
    p("\n[GATE 4] Leave-one-crisis-out {GFC,EuroDebt,COVID,Bear2022} + within-window cut")
    full_red = (_maxdd(net.values) - _maxdd(bh_net.values)) * 100
    p(f"  FULL-SAMPLE global DD-reduction = {full_red:+.1f}pp")
    crisis_hits = 0; crisis_cut_all = True
    p(f"  {'crisis':9} {'stratDD':>8} {'bhDD':>7} {'reduction':>10}")
    for cname, (c0, c1) in CRISES.items():
        win = (net.index >= c0) & (net.index <= c1)
        if win.sum() < 20:
            p(f"  {cname:9}: (outside sample / too short)")
            continue
        crisis_hits += 1
        tdd = _maxdd(net[win].values) * 100
        bdd = _maxdd(bh_net[win].values) * 100
        red = tdd - bdd; cut = red > 0
        if cname in LOCO_CRISES:
            crisis_cut_all = crisis_cut_all and cut
        p(f"  {cname:9} {tdd:8.1f} {bdd:7.1f} {red:+10.1f}  {'OK' if cut else 'FAIL'}{'' if cname in LOCO_CRISES else ' (non-LOCO)'}")
    p("  -- global-MaxDD row-deletion LOCO (drop each crisis, recompute global DD-reduction):")
    loco_global_ok = True
    for cname in LOCO_CRISES:
        c0, c1 = CRISES[cname]
        mask = ~((net.index >= c0) & (net.index <= c1))
        if mask.sum() < 252:
            continue
        red = (_maxdd(net[mask].values) - _maxdd(bh_net[mask].values)) * 100
        ok = red > 0
        loco_global_ok = loco_global_ok and ok
        p(f"     drop {cname:9}: global DD-reduction = {red:+.1f}pp  {'OK' if ok else 'FAIL'}")
    g4 = bool(crisis_cut_all and loco_global_ok)

    # GATE 5: beats dumb baselines (Sharpe + DD vs buy&hold AND flat-60/40)
    p("\n[GATE 5] Beats DUMB baselines (Sharpe AND MaxDD vs buy&hold + flat-60/40)")
    yrs = (net.index[-1] - net.index[0]).days / 365.25
    tdd = _maxdd(net.values) * 100; bdd = _maxdd(bh_net.values) * 100; fdd = _maxdd(flat_net.values) * 100
    tsh = _sharpe(net.values, TRADING_YEAR); bsh = _sharpe(bh_net.values, TRADING_YEAR); fsh = _sharpe(flat_net.values, TRADING_YEAR)
    p(f"  strat : Sharpe {tsh:.3f}  MaxDD {tdd:.1f}%  CAGR {cagr((1+net).cumprod(), yrs):.2f}%")
    p(f"  bh    : Sharpe {bsh:.3f}  MaxDD {bdd:.1f}%  CAGR {cagr((1+bh_net).cumprod(), yrs):.2f}%")
    p(f"  flat6040: Sharpe {fsh:.3f}  MaxDD {fdd:.1f}%  CAGR {cagr((1+flat_net).cumprod(), yrs):.2f}%")
    beats_sharpe = (tsh > bsh) and (tsh > fsh)
    cuts_dd = (tdd > bdd) and (tdd > fdd)
    p(f"  beats both on Sharpe: {beats_sharpe}   cuts DD vs both: {cuts_dd}")
    # post-2010 stress (drop GFC megabear)
    post = net.index >= pd.Timestamp("2010-01-01")
    if post.sum() > 252:
        psh_t = _sharpe(net[post].values, TRADING_YEAR); psh_b = _sharpe(bh_net[post].values, TRADING_YEAR)
        pdd_t = _maxdd(net[post].values) * 100; pdd_b = _maxdd(bh_net[post].values) * 100
        p(f"  POST-2010 (drop GFC): strat Sh {psh_t:.3f} DD {pdd_t:.1f}%  |  bh Sh {psh_b:.3f} DD {pdd_b:.1f}%")
        g5_post = bool(psh_t >= psh_b)
    else:
        g5_post = False
    g5 = bool(beats_sharpe and cuts_dd)

    # GATE 6: honest-N
    p("\n[GATE 6] Honest-N")
    p(f"  independent crisis eras IN sample = {crisis_hits} of {len(CRISES)}")
    p(f"  members correlated in crises -> NOT independent bets; effective-N ~= crisis count")
    g6 = bool(crisis_hits >= 4)

    gates = {
        "DSR>=0.90 (pooled)": g1,
        "DD-reduction CI excludes 0": g2,
        "same-sign split-half (DD)": g3,
        "leave-one-crisis-out holds": g4,
        "beats dumb baseline": g5,
        "honest-N adequate": g6,
    }
    p("\n  GATE SUMMARY:")
    for k, v in gates.items():
        p(f"    [{'PASS' if v else 'FAIL'}] {k}")
    p(f"  secondary: split-half SHARPE edge same-sign = {ss_sharpe}  |  Sharpe survives post-2010 = {g5_post}  |  DSR>=0.95 = {bool(dsr and dsr['dsr']>=0.95)}")

    return {"gates": gates, "dsr": dsr, "ss_sharpe": ss_sharpe, "ss_dd": ss_dd,
            "g2": g2, "g4": g4, "g5_post": g5_post, "ddred": ddred,
            "full_red": full_red, "crisis_hits": crisis_hits}


if __name__ == "__main__":
    main()
