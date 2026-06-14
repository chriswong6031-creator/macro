"""Phase-0 validation of the two-gate "dislocation" thesis (READ-ONLY research).

Writes nothing to the engine, latest.json or config. Measures whether the
dashboard's existing capitulation/dislocation signals carry a tradeable edge once
judged the HONEST way: hit-rate AND conditional max-drawdown, episode-declustered,
split-half OOS, and benchmarked against the AQR "buy the dips" null (= the
all-days base rate, i.e. just staying fully invested).

HARDENED (Phase 0b). Phase 0a found: (1) unconditional dip-buying does NOT beat
passive (AQR confirmed); (2) the regime VETO cuts drawdown but its return-edge
INVERTS out-of-sample (strong 1997-2011, gone 2012-2025) because the post-2009
Fed-PUT regime rescued the knife-looking dips. So this version makes the FED-PUT
the MASTER SWITCH and asks the sharper questions:

  * does PUT-ABSENT (recession OR inflation-locks-easing) cleanly mark the
    falling-knife regime, with deeper conditional drawdown, in BOTH halves?
  * is the drawdown separation ROBUST to the tiny effective sample? -> a 95% CI
    from an EPISODE BLOCK BOOTSTRAP (resample the declustered crisis episodes),
    plus LEAVE-ONE-YEAR-OUT sign consistency (the memory lesson: lean on
    sign-consistency across crises, not the p-value).
  * does the primary-trend leg add anything ON TOP of the put switch?

Master switch:
  recession  = real-time Sahm >= 0.50
  fedput_off = sustained 10y breakeven >= 2.5%  (inflation expectations block easing)
  PUT-ABSENT = recession OR fedput_off           (the knife regime; stand aside)
  PUT-PRESENT= neither                            (dips tend to be rescued/buyable)

Everything is computed from engine.inputs.build_features() +
engine.conditions.conditions_frame(), the SAME pipeline the live engine uses.
Run:  ./.venv/bin/python scripts/research_dislocation.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import warnings  # noqa: E402

warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from engine.conditions import conditions_frame  # noqa: E402
from engine.inputs import build_features  # noqa: E402
from lib import store  # noqa: E402

FAST = "--fast" in sys.argv          # skip the slow bootstrap/LOYO while iterating
HORIZONS = [21, 63, 126, 252]
HEADLINE_H = 63
ANALYSIS_START = "1997-01-01"
SPLIT_DATE = "2012-01-01"
EPISODE_GAP_BD = 42
SAHM_TRIGGER = 0.50
FEDPUT_BE = 2.5
N_BOOT = 5000
SEED = 12345
OUT_MD = Path(__file__).resolve().parent.parent / "research" / "DISLOCATION_VALIDATION.md"

_report: list[str] = []


def emit(line: str = "") -> None:
    print(line)
    _report.append(line)


# --------------------------------------------------------------------------- #
def forward_tables(spy: pd.Series) -> tuple[dict, dict]:
    fwd_ret, maxdd = {}, {}
    for h in HORIZONS:
        fwd_ret[h] = spy.shift(-h) / spy - 1.0
        maxdd[h] = spy.rolling(h).min().shift(-h) / spy - 1.0   # worst trough from entry
    return fwd_ret, maxdd


def master_switch(f: pd.DataFrame) -> dict[str, pd.Series]:
    be21 = f["breakeven_10y"].rolling(21, min_periods=10).mean()
    recession = (f["sahm"] >= SAHM_TRIGGER).fillna(False)
    fedput_off = (be21 >= FEDPUT_BE).fillna(False)                      # pre-2003 -> put ON
    spy = f["SPY"]
    downtrend = (spy.rolling(200, min_periods=120).mean().diff(21) <= 0).fillna(False)
    put_absent = recession | fedput_off
    return {"recession": recession, "fedput_off": fedput_off, "downtrend": downtrend,
            "put_absent": put_absent, "put_present": ~put_absent}


def triggers(f: pd.DataFrame, cf: pd.DataFrame) -> dict[str, pd.Series]:
    spy = f["SPY"]
    roll_max = spy.rolling(252, min_periods=120).max()
    vr = f["vix_ratio"]
    t = {
        "DIP>10%": spy < 0.90 * roll_max,
        "VIX>30": f["vix"] > 30,
        "VRP pctile>0.90": cf["vrp_pctile"] > 0.90,
        "VIX backwardation": vr > 1.0,
    }
    # composite STRESS = the union of the big stress signatures (best effective-N
    # for the bootstrap), declustered into crisis episodes downstream.
    t["STRESS (composite)"] = (f["vix"] > 30) | (spy < 0.88 * roll_max) | (cf["vrp_pctile"] > 0.90)
    return t


# --------------------------------------------------------------------------- #
def gate2_signals(f: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Gate-2 re-entry CONFIRMS (coincident, lag the low by construction):
    - hook   = VIX/VIX3M un-inverts, confirmed 2 closes (backwardation -> contango)
    - thrust = Zweig-style breadth thrust on adv/(adv+dec) (NOT up-volume — the
               breadth store has no volume; honest proxy), 10d EMA <0.40 -> >0.615."""
    vr = f["vix_ratio"]
    hook = ((vr < 1.0) & (vr.shift(1) < 1.0) & (vr.shift(2) >= 1.0)).fillna(False)
    thrust = pd.Series(False, index=f.index)
    br = store.read("breadth", "breadth")
    if br is not None and {"adv", "dec"} <= set(br.columns):
        ar = (br["adv"] / (br["adv"] + br["dec"])).reindex(f.index).ffill(limit=3)
        ema = ar.ewm(span=10, min_periods=5).mean()
        was_low = ema.shift(1).rolling(10, min_periods=3).min() < 0.40
        thrust = ((ema > 0.615) & (ema.shift(1) <= 0.615) & was_low).fillna(False)
    return hook, thrust


def episodes(mask: pd.Series, gap: int = EPISODE_GAP_BD) -> pd.Series:
    m = mask.fillna(False)
    prior = m.shift(1).rolling(gap, min_periods=1).max().fillna(0).astype(bool)
    return m & ~prior


def _metric(idx: pd.DatetimeIndex, fwd_ret, maxdd, h: int, metric: str) -> float:
    fr = fwd_ret[h].reindex(idx).dropna()
    dd = maxdd[h].reindex(idx).dropna()
    if len(fr) == 0:
        return np.nan
    if metric == "hit":
        return float((fr > 0).mean()) * 100
    if metric == "medret":
        return float(fr.median()) * 100
    if metric == "meddd":
        return float(dd.median()) * 100
    if metric == "p10dd":
        return float(dd.quantile(0.10)) * 100
    raise ValueError(metric)


def stats(entry: pd.Series, fwd_ret, maxdd, h: int) -> dict:
    idx = entry[entry].index
    n = int(fwd_ret[h].reindex(idx).notna().sum())
    return {"n": n, "hit": _metric(idx, fwd_ret, maxdd, h, "hit"),
            "med": _metric(idx, fwd_ret, maxdd, h, "medret"),
            "meddd": _metric(idx, fwd_ret, maxdd, h, "meddd"),
            "p10dd": _metric(idx, fwd_ret, maxdd, h, "p10dd")}


def fmt(label, s, w=22) -> str:
    if s["n"] == 0:
        return f"  {label:<{w}} (no events)"
    return (f"  {label:<{w}} n={s['n']:>3}  hit={s['hit']:5.1f}%  medRet={s['med']:+6.1f}%  "
            f"medDD={s['meddd']:+6.1f}%  p10DD={s['p10dd']:+7.1f}%")


def _entry_arrays(idx, fwd_ret, maxdd, h):
    """The (fwd-return, max-drawdown) pairs at a bucket's entries, once — so the
    bootstrap resamples plain arrays (no pandas reindex in the hot loop)."""
    fr = fwd_ret[h].reindex(idx); dd = maxdd[h].reindex(idx)
    ok = fr.notna() & dd.notna()
    return fr[ok].to_numpy(), dd[ok].to_numpy()


def _arr_metric(fr, dd, metric: str) -> float:
    if len(fr) == 0:
        return np.nan
    if metric == "hit":
        return float((fr > 0).mean()) * 100
    if metric == "medret":
        return float(np.median(fr)) * 100
    if metric == "meddd":
        return float(np.median(dd)) * 100
    if metric == "p10dd":
        return float(np.percentile(dd, 10)) * 100
    raise ValueError(metric)


def bootstrap_diff(buy_idx, veto_idx, fwd_ret, maxdd, h, metric, B=N_BOOT, seed=SEED):
    """Episode block bootstrap: resample the declustered crisis episodes (each
    episode = one ~independent block) with replacement; CI on present-minus-absent."""
    frb, ddb = _entry_arrays(buy_idx, fwd_ret, maxdd, h)
    frv, ddv = _entry_arrays(veto_idx, fwd_ret, maxdd, h)
    if len(frb) < 3 or len(frv) < 3:
        return (np.nan, np.nan, np.nan)
    rng = np.random.default_rng(seed)
    out = np.empty(B)
    for k in range(B):
        ib = rng.integers(0, len(frb), len(frb))
        iv = rng.integers(0, len(frv), len(frv))
        out[k] = _arr_metric(frb[ib], ddb[ib], metric) - _arr_metric(frv[iv], ddv[iv], metric)
    return tuple(np.percentile(out, [2.5, 50, 97.5]))


# --------------------------------------------------------------------------- #
def main() -> None:
    f = build_features()
    cf = conditions_frame(f).reindex(f.index)
    f = f.loc[ANALYSIS_START:]
    cf = cf.loc[ANALYSIS_START:]
    spy = f["SPY"]
    fwd_ret, maxdd = forward_tables(spy)
    M = master_switch(f)
    trig = triggers(f, cf)
    base = spy.notna() & spy.shift(-HEADLINE_H).notna()

    emit("=" * 100)
    emit(f"DISLOCATION VALIDATION (hardened) — SPY {f.index.min().date()}..{f.index.max().date()}")
    emit("  MASTER SWITCH: PUT-ABSENT = recession(Sahm>=0.5) OR fedput_off(sust. 10y breakeven>=2.5%)")
    emit("  honest lens: hit-rate AND conditional max-drawdown · episode-declustered · "
         "bootstrap CI · split-half · LOYO")
    emit("=" * 100)

    emit("\n### AQR NULL — buying a RANDOM day (the 'stay fully invested' bar to beat)")
    for h in HORIZONS:
        emit(fmt(f"all days ({h}d)", stats(base, fwd_ret, maxdd, h)))

    emit("\n### master-switch coverage")
    for nm in ("recession", "fedput_off", "downtrend"):
        emit(f"  {nm:<12} true on {M[nm].mean()*100:5.1f}% of days")
    emit(f"  PUT-ABSENT   on {M['put_absent'].mean()*100:5.1f}% of days  "
         f"=> PUT-PRESENT {M['put_present'].mean()*100:.1f}%")

    # --- core: does PUT-PRESENT vs PUT-ABSENT separate? ----------------------
    emit("\n" + "=" * 100)
    emit(f"MASTER-SWITCH TEST — stress episodes split by Fed-put state ({HEADLINE_H}d & 252d)")
    emit("=" * 100)
    for tname, tmask in trig.items():
        tmask = tmask.reindex(f.index).fillna(False)
        present = episodes(tmask & M["put_present"])
        absent = episodes(tmask & M["put_absent"])
        if int(episodes(tmask).sum()) == 0:
            continue
        emit(f"\n[{tname}]")
        for h in (HEADLINE_H, 252):
            emit(f"  -- {h}d --")
            emit(fmt("PUT-PRESENT (buyable)", stats(present, fwd_ret, maxdd, h)))
            emit(fmt("PUT-ABSENT (stand aside)", stats(absent, fwd_ret, maxdd, h)))

    sc = trig["STRESS (composite)"].reindex(f.index).fillna(False)
    present = episodes(sc & M["put_present"]); absent = episodes(sc & M["put_absent"])
    pi, ai = present[present].index, absent[absent].index
    if not FAST:
        # --- bootstrap CI on the composite STRESS separation ----------------
        emit("\n" + "=" * 100)
        emit(f"EPISODE BLOCK BOOTSTRAP — 95% CI on (PUT-PRESENT minus PUT-ABSENT), STRESS composite, "
             f"B={N_BOOT}")
        emit("  drawdown diff > 0  => present-bucket trough is SHALLOWER (the veto reduces path pain)")
        emit("=" * 100)
        emit(f"  n: PUT-PRESENT={len(pi)} episodes, PUT-ABSENT={len(ai)} episodes")
        for h in (HEADLINE_H, 252):
            emit(f"  -- {h}d --")
            for metric, lab, good in [("p10dd", "tail drawdown (p10)", ">0 shallower"),
                                      ("meddd", "median drawdown", ">0 shallower"),
                                      ("hit", "hit-rate", ">0 higher"),
                                      ("medret", "median return", ">0 higher")]:
                lo, md, hi = bootstrap_diff(pi, ai, fwd_ret, maxdd, h, metric)
                robust = "ROBUST" if (lo > 0 or hi < 0) else "spans 0"
                emit(f"    {lab:<22} diff={md:+6.1f}  95% CI [{lo:+6.1f}, {hi:+6.1f}]  "
                     f"({good}) -> {robust}")

    # --- does the trend leg add on top of the put switch? -------------------
    emit("\n" + "=" * 100)
    emit(f"DOES PRIMARY-TREND ADD ON TOP OF THE PUT SWITCH?  (PUT-PRESENT stress, {HEADLINE_H}d)")
    emit("=" * 100)
    emit(fmt("put-present & uptrend", stats(episodes(sc & M["put_present"] & ~M["downtrend"]),
                                            fwd_ret, maxdd, HEADLINE_H)))
    emit(fmt("put-present & downtrend", stats(episodes(sc & M["put_present"] & M["downtrend"]),
                                              fwd_ret, maxdd, HEADLINE_H)))

    # --- split-half on the put switch ---------------------------------------
    emit("\n" + "=" * 100)
    emit(f"SPLIT-HALF (OOS) — STRESS composite, PUT-PRESENT vs PUT-ABSENT, {HEADLINE_H}d")
    emit("=" * 100)
    for hlabel, hm in [("1997-2011", f.index < SPLIT_DATE), ("2012-2025", f.index >= SPLIT_DATE)]:
        hm = pd.Series(hm, index=f.index)
        emit(f"  {hlabel}:")
        emit(fmt("put-present", stats(episodes(sc & M["put_present"] & hm), fwd_ret, maxdd, HEADLINE_H), 14))
        emit(fmt("put-absent", stats(episodes(sc & M["put_absent"] & hm), fwd_ret, maxdd, HEADLINE_H), 14))

    # --- leave-one-year-out sign consistency on the drawdown edge -----------
    emit("\n" + "=" * 100)
    emit(f"LEAVE-ONE-YEAR-OUT — sign consistency of the tail-drawdown edge ({HEADLINE_H}d)")
    emit("  edge = p10DD(put-present) - p10DD(put-absent); >0 means present is shallower")
    emit("=" * 100)
    yrs = sorted({d.year for d in pi.union(ai)})
    holds = 0
    detail = []
    for y in yrs:
        keep_p = pi[pi.year != y]; keep_a = ai[ai.year != y]
        if len(keep_p) < 3 or len(keep_a) < 3:
            continue
        edge = _metric(keep_p, fwd_ret, maxdd, HEADLINE_H, "p10dd") - \
               _metric(keep_a, fwd_ret, maxdd, HEADLINE_H, "p10dd")
        holds += int(edge > 0)
        detail.append(y)
    full = _metric(pi, fwd_ret, maxdd, HEADLINE_H, "p10dd") - _metric(ai, fwd_ret, maxdd, HEADLINE_H, "p10dd")
    emit(f"  full-sample edge = {full:+.1f}pp;  sign holds dropping {holds}/{len(detail)} "
         f"of the crisis years ({detail[0]}..{detail[-1]})")

    # --- GATE-2 entry timer: does waiting for a confirm reduce path pain? ----
    emit("\n" + "=" * 100)
    emit(f"GATE-2 ENTRY TIMER — within BUYABLE-WASHOUT episodes, immediate vs wait-for-confirm ({HEADLINE_H}d)")
    emit("  hook = VIX term un-invert (2 closes); thrust = Zweig adv-ratio (no up-volume in store).")
    emit("  arms ONLY after Gate-1 buyable. A confirm that REDUCES drawdown at acceptable return cost = useful.")
    emit("=" * 100)
    hook, thrust = gate2_signals(f)
    hk_days, th_days = hook.to_numpy(), thrust.to_numpy()
    idx = f.index
    buy_ep = episodes(sc & M["put_present"])
    ep_dates = [e for e in buy_ep[buy_ep].index if e >= pd.Timestamp("2006-07-17")]  # hook needs vix3m
    H = 63
    imm_hk, hk_e, hk_lag, imm_th, th_e, th_lag = [], [], [], [], [], []
    for e in ep_dates:
        p = idx.get_loc(e)
        win = range(p + 1, min(p + 1 + H, len(idx)))
        hrel = [j for j in win if hk_days[j]]
        if hrel:
            imm_hk.append(e); hk_e.append(idx[hrel[0]]); hk_lag.append(hrel[0] - p)
        trel = [j for j in win if th_days[j]]
        if trel:
            imm_th.append(e); th_e.append(idx[trel[0]]); th_lag.append(trel[0] - p)

    def idx_stats(dts):
        s = pd.Series(False, index=idx)
        if len(dts):
            s.loc[pd.DatetimeIndex(dts)] = True
        return stats(s, fwd_ret, maxdd, HEADLINE_H)

    emit(f"  buyable episodes (2006+): {len(ep_dates)};  with a hook: {len(hk_e)} "
         f"(median lag {int(np.median(hk_lag)) if hk_lag else 0}d);  with a thrust: {len(th_e)} "
         f"(median lag {int(np.median(th_lag)) if th_lag else 0}d)")
    emit("  -- term-structure hook (matched subset) --")
    emit(fmt("immediate entry", idx_stats(imm_hk)))
    emit(fmt("wait for hook", idx_stats(hk_e)))
    emit("  -- breadth thrust (matched subset) --")
    emit(fmt("immediate entry", idx_stats(imm_th)))
    emit(fmt("wait for thrust", idx_stats(th_e)))

    # --- named-episode ledger ----------------------------------------------
    emit("\n" + "=" * 100)
    emit("NAMED-EPISODE LEDGER — entry = max-VIX day in window; put-state tag + outcome")
    emit("=" * 100)
    windows = [("1998 LTCM", "1998-08-01", "1998-10-31"), ("2000-02 dotcom", "2000-09-01", "2002-10-31"),
               ("2008 GFC", "2008-09-01", "2009-03-31"), ("2010 flash", "2010-05-01", "2010-07-31"),
               ("2011 EU/dgrade", "2011-08-01", "2011-10-31"), ("2015-16 China", "2015-08-01", "2016-02-29"),
               ("2018 volmaged", "2018-02-01", "2018-02-28"), ("2018Q4 selloff", "2018-10-01", "2018-12-31"),
               ("2020 COVID", "2020-02-19", "2020-03-31"), ("2022 bear", "2022-01-01", "2022-10-31"),
               ("2023 SVB", "2023-03-01", "2023-03-31"), ("2024 yen carry", "2024-08-01", "2024-08-31"),
               ("2025 tariff", "2025-04-01", "2025-04-30")]
    emit(f"  {'episode':<16}{'entry':<12}{'VIX':>4}{'Sahm':>6}{'be':>5}{'200d':>6}"
         f"{'put-state':>13}{'fwd63':>8}{'fwd252':>8}{'dd63':>7}{'dd252':>7}")
    for name, a, b in windows:
        win = f.loc[a:b]
        if win.empty or win["vix"].dropna().empty:
            emit(f"  {name:<16} (no data)"); continue
        e = win["vix"].idxmax()
        why = [k for k in ("recession", "fedput_off") if bool(M[k].get(e, False))]
        state = "PUT-ABSENT" if why else "put-present"
        trend = "up" if not M["downtrend"].get(e, False) else "DOWN"

        def gp(x):
            return "   n/a" if pd.isna(x) else f"{x*100:+.1f}%"
        emit(f"  {name:<16}{str(e.date()):<12}{f['vix'].get(e, np.nan):>4.0f}"
             f"{f['sahm'].get(e, np.nan):>6.2f}{f['breakeven_10y'].get(e, np.nan):>5.1f}"
             f"{trend:>6}{state:>13}"
             f"{gp(fwd_ret[63].get(e, np.nan)):>8}{gp(fwd_ret[252].get(e, np.nan)):>8}"
             f"{gp(maxdd[63].get(e, np.nan)):>7}{gp(maxdd[252].get(e, np.nan)):>7}"
             f"   {','.join(why)}")

    emit("\n" + "=" * 100)
    emit("READ-ME: a robust risk-filter shows the bootstrap drawdown-diff CI ENTIRELY > 0 and the "
         "LOYO sign holding across most crisis years. Return-diffs spanning 0 = no return edge (expected).")
    emit("=" * 100)

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("# Dislocation validation (Phase 0, hardened)\n\n```\n" + "\n".join(_report) + "\n```\n")
    print(f"\n[wrote {OUT_MD}]")


if __name__ == "__main__":
    main()
