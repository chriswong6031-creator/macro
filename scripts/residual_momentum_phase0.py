"""Residual momentum / trend quality / crash gating — Phase 0 honest measurement.

Three questions, in the order they should be asked:

  A. WINDOW SWEEP. Across the requested formation windows, does residual momentum
     (SUM of residuals, and its info-ratio form) rank forward winners — and does it
     beat the plain total-return control? Every window x construction x {raw,
     sector-neutral} cell is one trial; BH-FDR runs across the WHOLE grid, because
     testing 24 cells and reporting the best is how a null becomes a headline.

  B. TREND QUALITY. Do the nine measures predict anything on their own, and — the
     question that actually matters — do they add anything BEYOND residual momentum?
     A quality measure that only re-expresses momentum is a prettier momentum. This
     uses `incremental_ic`, which neutralizes each measure against the momentum score
     before scoring it.

  C. CRASH GATING. Does the six-condition gate improve the momentum sleeve's
     risk-adjusted return and drawdown — and does it beat the one-line
     Barroso-Santa-Clara vol-target baseline it has to justify itself against?

     This section REQUIRES the deep panel. The live cache starts in 2023 and contains
     no momentum crash; a crash gate measured there would grade itself on a sample
     with nothing to catch and report a confident null. `--closes live` therefore
     SKIPS section C with a printed reason rather than producing a vacuous pass.

Multiple testing is ledgered, not asserted: every candidate is logged to the Trial
Ledger at generation and the Deflated Sharpe reads its n from there.

Run:
  python3 -m scripts.residual_momentum_phase0 --closes deep --start 2002
  python3 -m scripts.residual_momentum_phase0 --closes live --factor-legs

Writes reports/residual-momentum-phase0.md. Pure harness — no site build, no commit.
"""
from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import momentum_crash_gate as gate  # noqa: E402
from engine import residual_momentum as rm  # noqa: E402
from engine import trend_quality as tq  # noqa: E402
from engine.equity_factors import _closes, _names_sectors  # noqa: E402
from engine.trial_ledger import TrialLedger  # noqa: E402
from engine.validation import (benjamini_hochberg, block_bootstrap_ci,  # noqa: E402
                               deflated_sharpe, dsr_verdict, ic_summary,
                               incremental_ic, rank_ic, ret_moments)
from engine.vol_managed import vol_scalar  # noqa: E402
from lib import config, store  # noqa: E402

COST_BPS = 5.0
FAMILY = "residual_momentum_phase0"


def _yahoo_ret(sym: str, index) -> pd.Series | None:
    df = store.read("yahoo", sym)
    if df is None or "close" not in df.columns:
        return None
    return df["close"].pct_change(fill_method=None).reindex(index)


def _panel(name: str) -> pd.DataFrame:
    p = config.data_dir() / "breadth" / f"{name}.parquet"
    if not p.exists():
        return pd.DataFrame()
    d = pd.read_parquet(p)
    d.index = pd.to_datetime(d.index)
    return d.sort_index()


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
# A. window sweep
# --------------------------------------------------------------------------- #
def window_sweep(R, eps, closes, sec, grid, horizon, ledger) -> dict:
    fwd = closes.pct_change(horizon, fill_method=None).shift(-horizon)
    wins = rm.distinct_windows()
    ics: dict[str, list] = {}
    sig_cache: dict[str, pd.DataFrame] = {}

    for wname, (form, skip) in wins.items():
        sigs = rm.window_signals(R, eps, form, skip)
        for sname, mat in sigs.items():
            sig_cache[f"{wname}|{sname}"] = mat
            ics[f"{wname}|{sname}"] = []
            ics[f"{wname}|{sname}|SN"] = []

    ledger.log_grid([{"section": "A", "window": w, "signal": s, "neutral": n,
                      "horizon": horizon}
                     for w in wins for s in ("mom_res", "ir_res", "mom_tot")
                     for n in (False, True)], family=FAMILY)

    for d in grid:
        if d not in fwd.index:
            continue
        fr = fwd.loc[d].dropna()
        if len(fr) < 25:
            continue
        for key, mat in sig_cache.items():
            if d not in mat.index:
                continue
            s = mat.loc[d].dropna()
            if len(s) < 25:
                continue
            ics[key].append(rank_ic(s, fr))
            g = sec.reindex(s.index)
            ics[f"{key}|SN"].append(rank_ic(s - s.groupby(g).transform("mean"), fr))

    rows, pvals = {}, {}
    for k, series in ics.items():
        summ = ic_summary(pd.Series(series).dropna(), periods_per_year=12)
        if summ.get("n", 0) >= 6:
            rows[k] = summ
            if summ.get("p_hac") is not None:
                pvals[k] = summ["p_hac"]
    for k, q in benjamini_hochberg(pvals, alpha=0.10).items():
        rows[k]["q_fdr"] = q["q"]
        rows[k]["survives_fdr"] = q["reject"]
    return {"ic": rows, "signals": sig_cache, "fwd": fwd, "n_trials": len(rows)}


# --------------------------------------------------------------------------- #
# B. trend quality
# --------------------------------------------------------------------------- #
def trend_quality_sweep(eps, closes, highs, lows, volumes, sec, grid, fwd,
                        mom_sig, *, form, skip, ledger, max_dates: int = 120) -> dict:
    """Per-measure IC + composite IC + INCREMENTAL IC over the momentum score.

    `max_dates` subsamples the rebalance grid (the battery is a per-name Python loop);
    the CAP AND THE DROPPED COUNT ARE REPORTED, because a silently truncated grid reads
    as full coverage."""
    all_m = list(tq.QUALITY_MEASURES) + list(tq.DIAGNOSTIC_MEASURES)
    ledger.log_grid([{"section": "B", "measure": m, "form": form, "skip": skip}
                     for m in all_m + ["composite"]], family=FAMILY)

    dates = grid
    dropped = 0
    if len(grid) > max_dates:                      # even stride, keeps era coverage
        step = int(np.ceil(len(grid) / max_dates))
        dates = grid[::step]
        dropped = len(grid) - len(dates)

    per: dict[str, list] = {m: [] for m in all_m + ["composite"]}
    sig_by_date, fwd_by_date, load_by_date = {}, {}, {}
    coverage: dict[str, int] = {m: 0 for m in all_m}

    for d in dates:
        if d not in fwd.index:
            continue
        fr = fwd.loc[d].dropna()
        if len(fr) < 25:
            continue
        t = tq.panel(eps, closes, form=form, skip=skip, highs=highs, lows=lows,
                     volumes=volumes, asof=d)
        if t.empty:
            continue
        t = t.reindex(fr.index).dropna(how="all")
        if len(t) < 25:
            continue
        fr2 = fr.reindex(t.index)
        for m in all_m:
            if m not in t.columns:
                continue
            col = t[m].dropna()
            coverage[m] += int(len(col))
            if len(col) >= 25:
                per[m].append(rank_ic(col, fr2.reindex(col.index)))
        comp = tq.composite(t, sectors=sec.reindex(t.index)).dropna()
        if len(comp) >= 25:
            per["composite"].append(rank_ic(comp, fr2.reindex(comp.index)))
            # incremental over the momentum score: is quality more than momentum again?
            if d in mom_sig.index:
                ms = mom_sig.loc[d].reindex(comp.index).dropna()
                if len(ms) >= 25:
                    sig_by_date[d] = comp.reindex(ms.index)
                    fwd_by_date[d] = fr2.reindex(ms.index)
                    load_by_date[d] = ms.to_frame("mom_res")

    rows, pvals = {}, {}
    for m, series in per.items():
        summ = ic_summary(pd.Series(series).dropna(), periods_per_year=12)
        if summ.get("n", 0) >= 6:
            rows[m] = summ
            if summ.get("p_hac") is not None:
                pvals[m] = summ["p_hac"]
    for m, q in benjamini_hochberg(pvals, alpha=0.10).items():
        rows[m]["q_fdr"] = q["q"]
        rows[m]["survives_fdr"] = q["reject"]

    inc = incremental_ic(sig_by_date, fwd_by_date, load_by_date, periods_per_year=12) \
        if sig_by_date else {}
    return {"ic": rows, "incremental": inc, "dates": len(dates), "dropped": dropped,
            "coverage": coverage}


# --------------------------------------------------------------------------- #
# C. crash gating
# --------------------------------------------------------------------------- #
def ls_returns(R, sig, grid, horizon):
    """Dollar-neutral top-vs-bottom-quintile EW sleeve; also returns the raw winner and
    loser leg series (the crash gate needs the loser leg for `loser_run`)."""
    w = pd.DataFrame(0.0, index=R.index, columns=R.columns)
    win_w = pd.DataFrame(0.0, index=R.index, columns=R.columns)
    lose_w = pd.DataFrame(0.0, index=R.index, columns=R.columns)
    for d in grid:
        if d not in sig.index:
            continue
        s = sig.loc[d].dropna()
        if len(s) < 25:
            continue
        top = s[s >= s.quantile(0.8)].index
        bot = s[s <= s.quantile(0.2)].index
        if len(top) and len(bot):
            w.loc[d, top] = 1.0 / len(top)
            w.loc[d, bot] = -1.0 / len(bot)
            win_w.loc[d, top] = 1.0 / len(top)
            lose_w.loc[d, bot] = 1.0 / len(bot)
    fill = lambda x: x.replace(0.0, np.nan).ffill().fillna(0.0)  # noqa: E731
    w, win_w, lose_w = fill(w), fill(win_w), fill(lose_w)
    Rc = R.clip(-0.5, 0.5)                      # garbage-tick guard (rank-IC is immune)
    gross = (w.shift(1) * Rc).sum(axis=1)
    turn = w.diff().abs().sum(axis=1)
    net = gross - (COST_BPS / 1e4) * turn
    return (net.loc[grid[0]:grid[-1]],
            (win_w.shift(1) * Rc).sum(axis=1).loc[grid[0]:grid[-1]],
            (lose_w.shift(1) * Rc).sum(axis=1).loc[grid[0]:grid[-1]])


def _stats(net: pd.Series, label: str, ledger) -> dict:
    net = net.dropna()
    if net.empty or not net.std():
        return {"label": label}
    cum = (1 + net).cumprod()
    out = {"label": label,
           "sharpe": round(float(net.mean() / net.std() * np.sqrt(252)), 2),
           "cum_pct": round(float((cum.iloc[-1] - 1) * 100), 1),
           "max_dd": round(float((cum / cum.cummax() - 1).min() * 100), 1),
           "skew": round(float(net.skew()), 2),
           "n_days": int(len(net))}
    mom = ret_moments(net)
    if mom:
        d = deflated_sharpe(mom[0], mom[1], mom[2], mom[3], ledger=ledger, family=FAMILY,
                            trading_year=252)
        if d:
            out["dsr"] = d["dsr"]
            out["verdict"] = dsr_verdict(d["dsr"])
    bc = block_bootstrap_ci(net, ann=252)
    if bc:
        out["sharpe_ci"] = bc["sharpe_ci"]
        out["sharpe_gt0_prob"] = bc["sharpe_gt0_prob"]
    return out


def sleeve_extension(net: pd.Series, win: int = 126) -> pd.Series:
    """'The signal is highly extended from its trend origin', measured on the momentum
    SLEEVE rather than per name — the gate sizes the sleeve, so the sleeve's own stretch
    is the relevant reading.

    Distance of the sleeve's cumulative log-NAV from its value `win` bars ago, scaled by
    the sleeve's own volatility over the same span. Deliberately NOT called ATR distance:
    the deep panel carries no high/low, and a close-only statistic wearing an ATR label
    would misreport what was measured."""
    nav = np.log((1.0 + net.fillna(0.0)).cumprod())
    span = nav - nav.shift(win)
    sd = net.rolling(win, min_periods=win // 2).std() * np.sqrt(win)
    return span / sd.replace(0, np.nan)


def _era_split(net: pd.Series, gated: pd.Series, volt: pd.Series, both: pd.Series,
               years: int = 6) -> list[dict]:
    """Per-era gated-vs-ungated comparison — the check that separates a real gate from
    ONE lucky episode.

    A crash gate is exactly the kind of signal that can post a great full-sample number
    off a single event (2008-09 for momentum) and nothing else. Splitting into fixed
    multi-year blocks and printing EVERY block, winners and losers, is what makes that
    visible: a gate that helps in one block out of four is a 2009 detector, not a gate."""
    if net.dropna().empty:
        return []
    rows = []
    start = net.index.min()
    while start < net.index.max():
        end = start + pd.DateOffset(years=years)
        sl = slice(start, end)
        n = net.loc[sl].dropna()
        if len(n) < 250:
            start = end
            continue

        def _sr(x):
            x = x.loc[sl].dropna()
            return round(float(x.mean() / x.std() * np.sqrt(252)), 2) if len(x) and x.std() else None

        def _dd(x):
            x = x.loc[sl].dropna()
            if not len(x):
                return None
            c = (1 + x).cumprod()
            return round(float((c / c.cummax() - 1).min() * 100), 1)

        # An era where the sleeve held NO positions (too few names to form quintiles
        # early in the deep panel) has zero-variance returns, not bad returns. Including
        # it would pad the denominator of "the gate wins in N of M eras" with blocks
        # where nothing was traded and no gate could have helped or hurt.
        if not n.std():
            start = end
            continue
        rows.append({"era": f"{start.year}–{min(end.year, net.index.max().year)}",
                     "n_days": int(len(n)),
                     "sr_ungated": _sr(net), "sr_gated": _sr(gated),
                     "sr_vol": _sr(volt), "sr_both": _sr(both),
                     "dd_ungated": _dd(net), "dd_both": _dd(both)})
        start = end
    return rows


def crash_section(R, closes, sig, grid, horizon, market, ledger, breadth=None,
                  extension=None) -> dict:
    net, win_leg, lose_leg = ls_returns(R, sig, grid, horizon)
    if extension is None:
        extension = sleeve_extension(net)
    ledger.log_grid([{"section": "C", "variant": v} for v in
                     ("ungated", "crash_gate", "vol_target", "gate_x_vol")], family=FAMILY)

    cond = gate.conditions(net, market_ret=market, panel_ret=R, loser_ret=lose_leg,
                           winner_ret=win_leg, breadth=breadth, extension=extension)
    exp = gate.exposure(cond, floor=0.0, cap=1.0)
    gated = net * exp.reindex(net.index).fillna(0.0)

    # Barroso-Santa-Clara baseline: scale by the sleeve's OWN realized vol.
    nav = (1 + net.fillna(0.0)).cumprod()
    vs = vol_scalar(nav, target=0.10, cap=1.0).shift(1).reindex(net.index).fillna(0.0)
    volt = net * vs
    both = net * exp.reindex(net.index).fillna(0.0) * vs

    live = exp.dropna()
    # Sharpe is scale-invariant, so a constant de-risking cannot change it. Reporting
    # mean exposure alongside the Sharpe lift is what shows the gain came from TIMING
    # rather than from simply holding less.
    return {
        "variants": [_stats(net, "ungated", ledger), _stats(gated, "crash-gated", ledger),
                     _stats(volt, "vol-target (Barroso)", ledger),
                     _stats(both, "gate x vol-target", ledger)],
        "eras": _era_split(net, gated, volt, both),
        "conditions_live": sorted(cond.columns) if not cond.empty else [],
        "conditions_absent": sorted(set(gate.CONDITIONS) - set(cond.columns)),
        "exposure_mean": round(float(live.mean()), 3) if len(live) else None,
        "exposure_span": (f"{live.index.min().date()}..{live.index.max().date()}"
                          if len(live) else None),
        "live_read": gate.live_read(cond, exp),
    }


# --------------------------------------------------------------------------- #
# D. factor-leg impact (descriptive)
# --------------------------------------------------------------------------- #
def legs_impact(closes, market, tkr_sector, legs, sec, *, win, shrink, form, skip) -> dict:
    """Does adding size/value/quality/low-vol to the regression CHANGE anything?

    Deliberately descriptive, not an IC test. The factor legs only exist on the ~3-year
    live panel (annual fundamentals), which yields ~1-2 dozen rebalances — far too few to
    say anything about predictive power, and an IC printed on that grid would invite
    exactly the over-reading it cannot support. What IS answerable at this sample size:
    how much residual variance the legs absorb, how much per-name factor exposure they
    remove, and whether the final ranking actually moves."""
    two = rm.residuals(closes, market, tkr_sector, win, shrink, None)
    three = rm.residuals(closes, market, tkr_sector, win, shrink, legs)
    warm = min(win + form, len(closes) - 60)
    t2, t3 = two.iloc[warm:], three.iloc[warm:]
    if t2.empty or t3.empty:
        return {}

    exposure = {}
    for name, leg in legs.items():
        l2 = leg.reindex(t2.index)
        exposure[name] = {
            "abs_corr_2leg": round(float(t2.corrwith(l2).abs().mean()), 4),
            "abs_corr_full": round(float(t3.corrwith(l2).abs().mean()), 4),
        }

    s2 = rm.window_signals(closes.pct_change(fill_method=None), two, form, skip)["mom_res"].iloc[-1]
    s3 = rm.window_signals(closes.pct_change(fill_method=None), three, form, skip)["mom_res"].iloc[-1]
    j = pd.concat([s2.rename("a"), s3.rename("b")], axis=1).dropna()
    sn = lambda s: s - s.groupby(sec.reindex(s.index)).transform("mean")  # noqa: E731
    top = lambda s, k=50: set(s.nlargest(k).index)  # noqa: E731
    return {
        "resid_vol_2leg": round(float(t2.std().mean()), 6),
        "resid_vol_full": round(float(t3.std().mean()), 6),
        "vol_absorbed_pct": round(float((1 - t3.std().mean() / t2.std().mean()) * 100), 2),
        "exposure": exposure,
        "score_rank_corr": round(float(sn(j["a"]).corr(sn(j["b"]), method="spearman")), 4)
        if len(j) >= 20 else None,
        "top50_overlap": (len(top(sn(j["a"])) & top(sn(j["b"]))) if len(j) >= 60 else None),
        "n_scored": int(len(j)),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--closes", choices=["live", "deep"], default="deep")
    ap.add_argument("--beta-win", type=int, default=252)
    ap.add_argument("--horizon", type=int, default=21)
    ap.add_argument("--shrink", type=float, default=0.66)
    ap.add_argument("--start", type=int, default=0, help="drop closes before this year")
    ap.add_argument("--factor-legs", action="store_true",
                    help="add size/value/quality/low-vol legs (live panel only)")
    ap.add_argument("--tq-form", type=int, default=252)
    ap.add_argument("--tq-skip", type=int, default=21)
    ap.add_argument("--max-tq-dates", type=int, default=120)
    ap.add_argument("--out", default="residual-momentum-phase0.md")
    args = ap.parse_args()

    closes = _panel("_closes_deep") if args.closes == "deep" else _closes()
    if closes is None or closes.empty:
        print(f"no {args.closes} close matrix — run scripts.residual_alpha_fetch for deep")
        return 1
    if args.start:
        closes = closes.loc[closes.index >= f"{args.start}-01-01"]
    closes = closes.loc[:, ~closes.columns.duplicated()].sort_index()

    ns = _names_sectors()
    tkr_sector = {t: ns.get(t, (t, "—"))[1] for t in closes.columns}
    keep = [t for t in closes.columns if tkr_sector.get(t, "—") != "—"]
    closes = closes[keep]
    sec = pd.Series({t: tkr_sector[t] for t in keep})
    market = _yahoo_ret("SPY", closes.index)
    if market is None or market.notna().sum() < 250:
        market = closes.pct_change(fill_method=None).mean(axis=1)   # EW fallback
        print("[warn] SPY unavailable — EW panel used as the market leg")

    legs = {}
    if args.factor_legs:
        legs = rm.factor_legs(closes)
        print(f"[legs] live: {sorted(legs) or 'NONE'}")

    ledger = TrialLedger(family=FAMILY)
    print(f"[panel] {args.closes} · {closes.shape[1]} names · "
          f"{closes.index.min().date()}..{closes.index.max().date()}")

    R = closes.pct_change(fill_method=None)
    print("[resid] building residuals …", flush=True)
    eps = rm.residuals(closes, market, tkr_sector, args.beta_win, args.shrink, legs)

    warmup = args.beta_win + 252 + 21
    grid = month_grid(R.index, warmup=warmup, horizon=args.horizon)
    if len(grid) < 12:
        print(f"grid too short ({len(grid)} rebalances)")
        return 1
    print(f"[grid]  {len(grid)} monthly rebalances {grid[0].date()}..{grid[-1].date()}",
          flush=True)

    print("[A] window sweep …", flush=True)
    A = window_sweep(R, eps, closes, sec, grid, args.horizon, ledger)

    print("[B] trend quality …", flush=True)
    highs, lows, volumes = (_panel("_high_cache"), _panel("_low_cache"), _panel("_volume_cache")) \
        if args.closes == "live" else (pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
    mom_sig = A["signals"].get("w12_1|mom_res")
    B = trend_quality_sweep(eps, closes, highs if len(highs) else None,
                            lows if len(lows) else None, volumes if len(volumes) else None,
                            sec, grid, A["fwd"], mom_sig, form=args.tq_form,
                            skip=args.tq_skip, ledger=ledger, max_dates=args.max_tq_dates)

    C = None
    if args.closes == "deep":
        print("[C] crash gating …", flush=True)
        bp = _panel("breadth")
        breadth = bp["pct_above_200"].reindex(R.index).ffill() \
            if not bp.empty and "pct_above_200" in bp.columns else None
        if breadth is None:
            print("[warn] no breadth panel — the breadth_rev condition stays absent")
        C = crash_section(R, closes, mom_sig, grid, args.horizon, market, ledger,
                          breadth=breadth)
    else:
        print("[C] SKIPPED — the live panel carries no momentum crash to gate.")

    D = None
    if legs:
        print("[D] factor-leg impact …", flush=True)
        D = legs_impact(closes, market, tkr_sector, legs, sec, win=args.beta_win,
                        shrink=args.shrink, form=args.tq_form, skip=args.tq_skip)

    report = render(A, B, C, D, args, closes, grid, legs, ledger)
    out = config.ROOT / config.load()["storage"]["reports_dir"] / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report)
    print(f"\n[report] {out}")
    return 0


def render(A, B, C, D, args, closes, grid, legs, ledger) -> str:
    L = ["# Residual momentum · trend quality · crash gating — Phase 0", "",
         "*Generated by `scripts/residual_momentum_phase0.py`. Judge every IC against ~0. "
         "BH-FDR(10%) runs across the WHOLE candidate grid, not per-row.*", "",
         f"Panel **{args.closes}** · {closes.shape[1]} names · "
         f"{closes.index.min().date()}..{closes.index.max().date()} · "
         f"{len(grid)} monthly rebalances ({grid[0].date()}..{grid[-1].date()}) · "
         f"beta {args.beta_win}d (shrink {args.shrink}) · forward {args.horizon}d.", ""]

    dup = rm.duplicate_windows()
    L += [f"**Windows tested:** {', '.join(f'`{k}`' for k in rm.distinct_windows())}. "
          + (f"`{'`, `'.join(dup)}` collapsed onto `{list(dup.values())[0]}` — "
             "\"12−1 months\" and \"12 months excluding the last 21 days\" are the same "
             "construction (form 252 / skip 21), so the five requested windows are FOUR "
             "distinct tests." if dup else ""), ""]
    L += [f"**Factor legs live:** {', '.join(sorted(legs)) if legs else 'NONE'}"
          + ("" if legs else " — market + sector only (the deep panel has no factor "
             "history; legs are reported absent, never imputed to zero)."), ""]

    L += ["## A. Window sweep", "",
          "| candidate | mean IC | IC-IR ann | t_HAC | p | q_FDR | hit | n |",
          "|---|--:|--:|--:|--:|--:|--:|--:|"]
    rows = A["ic"]
    for k in sorted(rows, key=lambda c: -(rows[c].get("mean_ic") or -9)):
        r = rows[k]
        L.append(f"| `{k}` | {r.get('mean_ic')} | {r.get('ic_ir_ann')} | {r.get('t_hac')} "
                 f"| {r.get('p_hac')} | {r.get('q_fdr','—')} | {r.get('hit')} | {r.get('n')} |")
    surv = [k for k in rows if rows[k].get("survives_fdr")]
    L += ["", f"**Survive BH-FDR(10%):** {', '.join(f'`{s}`' for s in surv) if surv else '**NONE**'}", ""]

    # Candidates scored on DIFFERENT date sets are not comparable. The residual needs a
    # populated sector cross-section, so early in the deep panel it has no cross-section
    # while total momentum already does — ranking the two side by side then compares a
    # modern sample against one that includes the pre-2000 era, which manufactures a
    # result. Flag it loudly rather than leaving it to be noticed.
    ns = {k: r.get("n") for k, r in rows.items() if r.get("n")}
    if ns and max(ns.values()) - min(ns.values()) > 0.1 * max(ns.values()):
        lo_k = min(ns, key=lambda k: ns[k])
        hi_k = max(ns, key=lambda k: ns[k])
        L += [f"> ⚠️ **Not an apples-to-apples table.** Candidates were scored on "
              f"materially different date counts (`{lo_k}` n={ns[lo_k]} vs `{hi_k}` "
              f"n={ns[hi_k]}). The residual signals need a populated sector "
              "cross-section, which the deep panel does not have in its earliest "
              "decades, so residual-vs-total rows here span different eras. **Use the "
              "modern-era report for that comparison** — there every candidate carries "
              "the same n.", ""]

    L += ["## B. Trend quality", "",
          f"Window form {args.tq_form}d / skip {args.tq_skip}d · {B['dates']} scored dates"
          + (f" (**{B['dropped']} rebalances dropped** by the `--max-tq-dates` cap — "
             "reported, not silently truncated)" if B["dropped"] else ""), "",
          "| measure | mean IC | IC-IR ann | t_HAC | q_FDR | n |", "|---|--:|--:|--:|--:|--:|"]
    br = B["ic"]
    for m in sorted(br, key=lambda c: -(br[c].get("mean_ic") or -9)):
        r = br[m]
        flag = " ⚠️ KILLED prior" if m in tq.DIAGNOSTIC_MEASURES else ""
        L.append(f"| `{m}`{flag} | {r.get('mean_ic')} | {r.get('ic_ir_ann')} "
                 f"| {r.get('t_hac')} | {r.get('q_fdr','—')} | {r.get('n')} |")
    absent = [m for m in list(tq.QUALITY_MEASURES) + list(tq.DIAGNOSTIC_MEASURES)
              if m not in br]
    survb = [m for m in br if br[m].get("survives_fdr")]
    L += ["", f"**Survive BH-FDR(10%):** {', '.join(f'`{s}`' for s in survb) if survb else '**NONE**'}"]
    if absent:
        L += ["", f"**Not scored (input absent on this panel):** {', '.join(f'`{m}`' for m in absent)} "
              "— `ud_vol` needs volume and `atr_dist` needs high/low, which the deep "
              "close-only panel does not carry."]
    inc = B.get("incremental") or {}
    if inc:
        raw, i2 = inc.get("raw", {}), inc.get("incremental", {})
        L += ["", "**Composite quality — does it survive neutralizing against residual momentum?**", "",
              "| | mean IC | t_HAC | n |", "|---|--:|--:|--:|",
              f"| raw | {raw.get('mean_ic')} | {raw.get('t_hac')} | {raw.get('n')} |",
              f"| neutralized vs `mom_res` | {i2.get('mean_ic')} | {i2.get('t_hac')} | {i2.get('n')} |",
              "", f"IC delta {inc.get('ic_delta')} · surviving fraction "
              f"{inc.get('surviving_frac')} — the share of the composite's edge that is "
              "NOT repackaged residual momentum."]
    L += [""]

    if C is None:
        L += ["## C. Crash gating", "",
              "**SKIPPED — not measurable on this panel.** The live cache begins in 2023 "
              "and contains no momentum crash, so a crash gate scored here would grade "
              "itself on a sample with nothing to catch. Re-run with `--closes deep`.", ""]
    else:
        L += ["## C. Crash gating", "",
              f"Conditions live: {', '.join(f'`{c}`' for c in C['conditions_live']) or 'none'}"
              + (f" · absent: {', '.join(f'`{c}`' for c in C['conditions_absent'])}"
                 if C["conditions_absent"] else "") + ".",
              f"Mean exposure {C['exposure_mean']} over {C['exposure_span']} — Sharpe is "
              "scale-invariant, so holding less on average cannot by itself move the "
              "Sharpe column; any lift there is TIMING.", "",
              "| variant | Sharpe | cum % | max DD % | skew | DSR | verdict | Sharpe CI | P(SR>0) |",
              "|---|--:|--:|--:|--:|--:|---|---|--:|"]
        for v in C["variants"]:
            L.append(f"| {v.get('label')} | {v.get('sharpe','—')} | {v.get('cum_pct','—')} "
                     f"| {v.get('max_dd','—')} | {v.get('skew','—')} | {v.get('dsr','—')} "
                     f"| {v.get('verdict','—')} | {v.get('sharpe_ci','—')} "
                     f"| {v.get('sharpe_gt0_prob','—')} |")
        L += ["", "The gate has to beat `vol-target (Barroso)`, not just `ungated` — "
              "one-line vol scaling is the cheap baseline six conditions must justify.", ""]
        if C.get("eras"):
            L += ["**Per-era — is this one episode?** A crash gate can post a great "
                  "full-sample number off a single event and nothing else. Every block "
                  "is printed, losers included.", "",
                  "| era | days | SR ungated | SR gated | SR vol-tgt | SR both | "
                  "maxDD ungated % | maxDD both % |", "|---|--:|--:|--:|--:|--:|--:|--:|"]
            for e in C["eras"]:
                L.append(f"| {e['era']} | {e['n_days']} | {e['sr_ungated']} | "
                         f"{e['sr_gated']} | {e['sr_vol']} | {e['sr_both']} | "
                         f"{e['dd_ungated']} | {e['dd_both']} |")
            n_era = len(C["eras"])
            wins = sum(1 for e in C["eras"] if (e["sr_both"] or -9) > (e["sr_ungated"] or -9))
            dd_wins = sum(1 for e in C["eras"]
                          if (e["dd_both"] or -99) > (e["dd_ungated"] or -99))
            L += ["", f"`gate x vol-target` beats `ungated` on Sharpe in **{wins} of "
                  f"{n_era}** eras and on max drawdown in **{dd_wins} of {n_era}**. "
                  "(Eras where the sleeve held no positions at all — too few names to "
                  "form quintiles early in the deep panel — are excluded rather than "
                  "padding the denominator with blocks no gate could have affected.)", ""]

    if D:
        L += ["## D. Factor-leg impact (descriptive)", "",
              "Does adding size / value / quality / low-vol to the regression change "
              "anything? **Descriptive on purpose** — the legs only exist on the ~3-year "
              "live panel (annual fundamentals), which is far too few rebalances to say "
              "anything about predictive power.", "",
              f"Mean residual vol {D['resid_vol_2leg']} (market+sector) → "
              f"{D['resid_vol_full']} (with legs) — **{D['vol_absorbed_pct']}%** of "
              "residual volatility absorbed.", "",
              "| leg | mean abs corr to residual, market+sector | with the leg in |",
              "|---|--:|--:|"]
        for name, e in sorted(D["exposure"].items()):
            L.append(f"| `{name}` | {e['abs_corr_2leg']} | {e['abs_corr_full']} |")
        L += ["", f"Sector-neutral score rank correlation between the two constructions: "
              f"**{D['score_rank_corr']}** over {D['n_scored']} names"
              + (f" · top-50 overlap {D['top50_overlap']}/50" if D["top50_overlap"] is not None
                 else "") + ".",
              "", "A high rank correlation means the extra legs mostly re-express what "
              "market+sector already removed; a low one means they change who the "
              "leaders are — and would then need their own promotion gate before "
              "anything acted on the difference.", ""]

    L += ["---", "",
          f"**Multiple testing.** {ledger.literal_n(FAMILY)} candidates logged to the Trial "
          f"Ledger for family `{FAMILY}`; the Deflated Sharpe reads its n from there rather "
          "than a caller-chosen literal.", "",
          "**Standing prior.** `resid_accel` (residual acceleration) was pre-registered and "
          "KILLED in the earlier residual-alpha work (deep-panel IC −0.012, t −2.7) and is "
          "carried here as a DIAGNOSTIC only — it is excluded from the quality composite by "
          "construction. Re-promoting it needs a fresh pre-registered gate.", ""]
    return "\n".join(L)


if __name__ == "__main__":
    # CLI-only: rolling betas on truncated history emit benign numpy/pandas warnings.
    # Kept under __main__ (the walk_forward.py idiom) because a module-level call would
    # mute the process-global filter for anything that merely imports this harness.
    warnings.filterwarnings("ignore")
    sys.exit(main())
