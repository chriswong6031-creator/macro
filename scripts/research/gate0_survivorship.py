"""GATE-0 — PIT-membership survivorship audit of the sector-confluence ladder.

See research/SECTOR_ROTATION_CONTINUATION.md (the handoff) and research/GATE0_SURVIVORSHIP.md
(the verdict this script feeds).

WHAT THE HANDOFF WORRIED ABOUT, AND WHY THE LITERAL FORM IS A NON-SEQUITUR.
The handoff frames GATE-0 as "re-derive the engine/sector_signals.py BUY/AVOID/SETUP
forward hit-rates on PIT constituents (not current) ... every cited number was computed
on CURRENT membership unless proven otherwise." But the shipped sector-confluence
numbers (engine/sector_signals.STATE_BASE_RATES; research/SECTOR_CONFLUENCE.md) were
measured on the **11 SPDR sector ETFs vs SPY** — the `calibrate()` loop iterates over
the ETFs, takes each ETF's own forward-63d return, and never touches a constituent
universe. ETF prices have **no membership**, so they cannot carry dead-name
survivorship bias; the handoff itself concedes "the 11 sector ETFs themselves are
survivorship-clean." The liquidity +6.4pp number (research/LIQUIDITY_LADDER.md) is a
fixed 141-instrument cross-asset panel (95%+ liquid indices/ETFs), likewise not an
S&P-1500 constituent backtest. So there is **no current-membership number to re-run**
for those headlines — they are clean by construction.

THE GENUINE QUESTION THIS AUDIT ANSWERS. Does the SAME validated state machine's edge
GENERALIZE from the 11 ETFs to the individual S&P-1500 constituent NAMES, and does it
survive on a delisting-inclusive, point-in-time universe rather than today's survivors?
That is the real survivorship test the PIT membership data lets us run, and it is the
stronger evidence: if the AVOID family is still negative across all four eras on names
that include the dead, the ETF-level VALIDATED label is corroborated, not merely
unfalsified.

METHOD. Identical rule for every universe — the engine's own `_verdict` (verbatim,
reused, never reimplemented), weekly-sampled, 200-day-gated, forward-63d EXCESS vs SPY
(plus ABSOLUTE), point-in-time (3-day flags forward-filled so date t uses only data
<= t, exactly as `calibrate()`):

  * BIASED   = today's surviving members, evaluated over ALL their price history
               (the classic survivorship-biased backfill: today's index, all history).
  * PIT      = the full historical roster INCLUDING delisted names, each evaluated
               ONLY within its actual membership window(s) (point-in-time correct).
  * SURV_WIN / DEAD_WIN = decomposition (survivors-windowed vs dead-names-windowed)
               to isolate the pure dead-name contribution from the windowing effect.

The BIASED->PIT delta is the survivorship + membership-look-ahead effect on the
NAME-LEVEL generalization of the signal.

VERDICT BAR (handoff). If the AVOID family's all-era negativity survives on PIT ->
the VALIDATED label holds (now with constituent + survivorship-clean support). If it
weakens materially, downgrade and re-scope downstream.

ROBUST STATISTICS (load-bearing). Delisted-name price series are riddled with penny-
stock artifacts: a name decaying to $0.02 then printing $0.40 makes c.shift(-63)/c
explode to +1900%, and un-split-adjusted dead tapes do the same. Raw pooled MEANS are
destroyed by these (the DEAD_WIN slice showed +800% means). So the headline statistic
here is the **MEDIAN** forward-63d excess (fully outlier-immune) with a winsorized mean
beside it (forward returns clipped to [-90%, +200%]). HIT-RATE is a sign-count and was
never affected. A level-based price floor is deliberately AVOIDED — these are dividend-
adjusted closes, so a $5 floor would wrongly delete the early history of every
multi-decade compounder.

HONEST CEILING (carried into the writeup). Only the 199 names in _closes_delisted have
post-exit prices (~18% of the 1083 ever-delisted roster names), and forward-63d returns
that run past a delisting are dropped (no -100% bankruptcy imputation here — that is
scripts/residual_alpha_pit.py's job). Both push the PIT result OPTIMISTIC (the worst of
the dead is under-sampled), so the PIT universe is ~95% survivors by row count and a
surviving-negative AVOID edge is a *lower bound* on the de-biasing — conservative for
the VALIDATED verdict, not against it.

Run:  python -m scripts.research.gate0_survivorship
Out:  data/research/gate0_survivorship.json  + a printed table.
"""
from __future__ import annotations

import json
from array import array
from collections import defaultdict

import numpy as np
import pandas as pd

import engine.sector_signals as ss
from lib import config, store

HORIZON = 63
CLIP = (-0.90, 2.00)                         # winsorize forward 63d returns (kills dead-name explosions)
START = pd.Timestamp("1998-01-01")          # match research/SECTOR_CONFLUENCE.md window
WARMUP = pd.Timedelta(days=420)             # 200d SMA + 3D resample warmup before START
ERAS = [("1998-2007", "1998-01-01", "2007-12-31"),
        ("2008-2015", "2008-01-01", "2015-12-31"),
        ("2016-2020", "2016-01-01", "2020-12-31"),
        ("2021-2026", "2021-01-01", "2026-12-31")]
# the engine's two families (OVERSOLD_BOUNCE is ETF-defensive-only, never fires here)
BUY_STATES = ["BUY", "BUY_PARTIAL", "SETUP_BUY"]
AVOID_STATES = ["EXTENDED", "TOPPING", "SELL"]
# the columns _verdict reads off each daily (d) and 3-day (t3) flag row
FCOLS = ["rsi", "stoch", "macd_up", "stoch_up", "setup_up",
         "macd_dn", "stoch_dn", "setup_dn", "stoch_roll", "rsi_roll"]


def era_of(ts: pd.Timestamp):
    for name, lo, hi in ERAS:
        if pd.Timestamp(lo) <= ts <= pd.Timestamp(hi):
            return name
    return None


def load_inputs():
    dd = config.data_dir()
    pit = pd.read_parquet(dd / "breadth" / "sp1500_pit_membership.parquet")
    pit["start_date"] = pd.to_datetime(pit["start_date"])
    pit["end_date"] = pd.to_datetime(pit["end_date"])
    deep = pd.read_parquet(dd / "breadth" / "_closes_deep.parquet")
    deld = pd.read_parquet(dd / "breadth" / "_closes_delisted.parquet")
    for df in (deep, deld):
        df.index = pd.to_datetime(df.index)
    # union columns; deep preferred where a ticker appears in both
    extra = [c for c in deld.columns if c not in deep.columns]
    combined = deep.join(deld[extra], how="outer").sort_index()
    combined = combined[[c for c in combined.columns if c != "Date"]]
    spy = store.read("yahoo", "SPY")["close"].dropna()
    spy.index = pd.to_datetime(spy.index)
    # membership windows + survivor flag (any open span = still in an index)
    windows: dict[str, list] = defaultdict(list)
    survivor: dict[str, bool] = {}
    for r in pit.itertuples(index=False):
        windows[r.ticker].append((r.start_date, r.end_date))
        survivor[r.ticker] = survivor.get(r.ticker, False) or pd.isna(r.end_date)
    return combined, spy, windows, survivor, pit


def run():
    combined, spy, windows, survivor, pit = load_inputs()
    roster = set(windows)
    have_px = [t for t in combined.columns if t in roster]
    # key = (universe, era, state) -> winsorized excess / absolute value streams (float32)
    acc_exc: dict = defaultdict(lambda: array("f"))
    acc_abs: dict = defaultdict(lambda: array("f"))
    cov = {"roster": len(roster), "with_prices": 0, "dead_total": 0, "dead_with_prices": 0,
           "evaluated_names": 0, "clip": list(CLIP)}
    dead_roster = {t for t in roster if not survivor.get(t, False)}
    cov["dead_total"] = len(dead_roster)
    cov["with_prices"] = len(have_px)
    cov["dead_with_prices"] = len([t for t in have_px if t in dead_roster])
    lo, hi = CLIP

    for t in have_px:
        c = combined[t].dropna()
        c = c[c.index >= (START - WARMUP)]
        if len(c) < 400:
            continue
        c3 = c.resample(ss.TF3).last().dropna()
        if len(c3) < 40:
            continue
        df = ss._flag_frame(c)
        df3 = ss._flag_frame(c3).reindex(c.index, method="ffill")
        sma200 = c.rolling(200).mean()
        sp = spy.reindex(c.index).ffill()
        fwd = (c.shift(-HORIZON) / c - 1)
        spy_fwd = (sp.shift(-HORIZON) / sp - 1)
        # numpy views for the hot loop
        d_arr = {k: df[k].to_numpy() for k in FCOLS}
        t3_arr = {k: df3[k].to_numpy() for k in FCOLS}
        cv, s2v = c.to_numpy(), sma200.to_numpy()
        fwdv = np.clip(fwd.to_numpy(), lo, hi)          # WINSORIZE the name's forward return (kills dead-name explosions)
        spyv = spy_fwd.to_numpy()                        # SPY 63d return is bounded; never winsorize the benchmark
        excv = fwdv - spyv
        rsi3 = t3_arr["rsi"]
        idx = c.index
        is_surv = bool(survivor.get(t, False))
        wins = windows[t]
        used = False
        for i in range(200, len(c) - HORIZON, 5):          # weekly sample, PIT
            e = excv[i]
            if not np.isfinite(e) or not np.isfinite(fwdv[i]) or not np.isfinite(rsi3[i]):
                continue
            ts = idx[i]
            if ts < START:
                continue
            era = era_of(ts)
            if era is None:
                continue
            s2 = s2v[i]
            above = bool(cv[i] > s2) if np.isfinite(s2) else True
            depth = (cv[i] / s2 - 1) if (np.isfinite(s2) and s2) else None
            slope = bool(i >= 221 and np.isfinite(s2v[i - 21]) and (s2 - s2v[i - 21]) >= 0)
            d = {k: d_arr[k][i] for k in FCOLS}
            t3 = {k: t3_arr[k][i] for k in FCOLS}
            state = ss._verdict(d, t3, above, True, depth200=depth,
                                slope200_up=slope, osb_eligible=False)["state"]
            a = float(fwdv[i])
            e = float(e)
            in_win = any((st <= ts) and (pd.isna(en) or ts <= en) for st, en in wins)
            for uni, inc in (("BIASED", is_surv), ("PIT", in_win),
                             ("SURV_WIN", is_surv and in_win),
                             ("DEAD_WIN", (not is_surv) and in_win)):
                if not inc:
                    continue
                for ek in (era, "ALL"):
                    acc_exc[(uni, ek, state)].append(e)
                    acc_abs[(uni, ek, state)].append(a)
            used = True
        if used:
            cov["evaluated_names"] += 1
    return acc_exc, acc_abs, cov


def _stat(exc, abs_):
    """Robust per-bucket stats from winsorized value streams. MEDIAN is the headline
    (outlier-immune); mean is winsorized; hit is a sign-count (never affected)."""
    n = len(exc)
    if n == 0:
        return None
    e = np.frombuffer(exc, dtype="f4")
    a = np.frombuffer(abs_, dtype="f4")
    return {"exc_med": round(float(100 * np.median(e)), 3),
            "exc_mean": round(float(100 * e.mean()), 3),
            "hit": round(float(100 * (e > 0).mean()), 1),
            "abs_med": round(float(100 * np.median(a)), 3),
            "abs_hit": round(float(100 * (a > 0).mean()), 1),
            "n": n}


def summarize(acc_exc, acc_abs):
    out: dict = {}
    for (uni, era, state), exc in acc_exc.items():
        s = _stat(exc, acc_abs[(uni, era, state)])
        if s:
            out.setdefault(uni, {}).setdefault(era, {})[state] = s
    # family rollups: concatenate the member states' value streams per universe/era
    fam_exc: dict = defaultdict(list)
    fam_abs: dict = defaultdict(list)
    for (uni, era, state), exc in acc_exc.items():
        for famname, members in (("BUY_SIDE", BUY_STATES), ("AVOID_SIDE", AVOID_STATES)):
            if state in members:
                fam_exc[(uni, era, famname)].append(np.frombuffer(exc, dtype="f4"))
                fam_abs[(uni, era, famname)].append(np.frombuffer(acc_abs[(uni, era, state)], dtype="f4"))
    for k, parts in fam_exc.items():
        uni, era, famname = k
        e = np.concatenate(parts)
        a = np.concatenate(fam_abs[k])
        out.setdefault(uni, {}).setdefault(era, {})[famname] = {
            "exc_med": round(float(100 * np.median(e)), 3), "exc_mean": round(float(100 * e.mean()), 3),
            "hit": round(float(100 * (e > 0).mean()), 1),
            "abs_med": round(float(100 * np.median(a)), 3), "abs_hit": round(float(100 * (a > 0).mean()), 1),
            "n": int(e.size)}
    return out


def _fmt_row(label, s):
    if not s:
        return f"  {label:<14} {'—':>52}"
    return (f"  {label:<14} med={s['exc_med']:+6.2f}%  mean={s['exc_mean']:+6.2f}%  "
            f"hit={s['hit']:>4.1f}%  abs_med={s['abs_med']:+6.2f}%  n={s['n']:>6}")


def print_report(summ, cov):
    print("\n" + "=" * 78)
    print("GATE-0 — sector-confluence ladder, NAME-LEVEL PIT survivorship audit")
    print("=" * 78)
    print(f"roster={cov['roster']}  with_prices={cov['with_prices']}  "
          f"evaluated_names={cov['evaluated_names']}")
    print(f"dead_names={cov['dead_total']}  dead_with_prices={cov['dead_with_prices']} "
          f"({100 * cov['dead_with_prices'] // max(cov['dead_total'], 1)}% coverage — honest ceiling)")
    order = ["BUY_SIDE", "BUY", "BUY_PARTIAL", "SETUP_BUY", "NEUTRAL",
             "AVOID_SIDE", "EXTENDED", "TOPPING", "SELL", "BELOW_TREND"]
    for uni in ["BIASED", "PIT", "SURV_WIN", "DEAD_WIN"]:
        if uni not in summ:
            continue
        print(f"\n### {uni}")
        for era in ["ALL"] + [e[0] for e in ERAS]:
            ed = summ[uni].get(era)
            if not ed:
                continue
            print(f"  -- {era} --")
            for st in order:
                if st in ed:
                    print(_fmt_row(st, ed[st]))
    # the verdict-bar line: AVOID_SIDE - BUY_SIDE median spread across eras (the
    # original "cross-sectional BUY-side minus AVOID-side" robustness test, name-level)
    print("\n" + "-" * 78)
    for metric, mname in (("exc_med", "MEDIAN"), ("exc_mean", "winsor-MEAN")):
        print(f"VERDICT BAR [{mname}] — AVOID_SIDE by era (a 'don't-chase' edge wants AVOID < BUY):")
        for uni in ["BIASED", "PIT"]:
            arow, brow = [], []
            for e in ERAS:
                sa = summ.get(uni, {}).get(e[0], {}).get("AVOID_SIDE")
                sb = summ.get(uni, {}).get(e[0], {}).get("BUY_SIDE")
                arow.append(f"{e[0].split('-')[0]}={sa[metric]:+.2f}" if sa else "NA")
                brow.append(f"{e[0].split('-')[0]}={sb[metric]:+.2f}" if sb else "NA")
            spreads = []
            allneg = True
            for e in ERAS:
                sa = summ.get(uni, {}).get(e[0], {}).get("AVOID_SIDE")
                sb = summ.get(uni, {}).get(e[0], {}).get("BUY_SIDE")
                if sa and sb:
                    sp = sb[metric] - sa[metric]
                    spreads.append(f"{e[0].split('-')[0]}={sp:+.2f}")
                    if sp <= 0:
                        allneg = False
            print(f"  {uni:<8} AVOID[{'  '.join(arow)}]")
            print(f"  {uni:<8} BUY  [{'  '.join(brow)}]")
            print(f"  {uni:<8} BUY-AVOID spread[{'  '.join(spreads)}]  buy>avoid_all4={allneg}")
        print()


def main():
    acc_exc, acc_abs, cov = run()
    summ = summarize(acc_exc, acc_abs)
    out = {"meta": {"horizon": HORIZON, "start": str(START.date()), "eras": [e[0] for e in ERAS],
                    "coverage": cov,
                    "note": "name-level generalization + PIT survivorship test of the "
                            "ETF-validated engine.sector_signals state machine"},
           "results": summ}
    outp = config.data_dir() / "research" / "gate0_survivorship.json"
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(out, indent=2))
    print_report(summ, cov)
    print(f"\nwrote {outp}")


if __name__ == "__main__":
    main()
