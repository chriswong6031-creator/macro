"""Per-leg isolation of the not-topped veto — the measurement the family-level null cannot make.

Charter: W5.1 macd_bear ratification packet (research/prophet_us_audit/
MACD_BEAR_RATIFICATION_PACKET.md). MEASUREMENT ONLY. No gate, board, engine or config
change follows from this file; the W5 change stays sequenced behind G0.2 (five green
nightly miss-audits) AND operator ratification.

WHY THIS INSTRUMENT EXISTS. Two prior measurements bound the veto FAMILY:

  * `label_grading_battery.py` (#4547) graded `not_topped:macd_bear_ONLY`, where ONLY
    means leg-exclusive WITHIN the not-topped triple (l.649-651: `mb & ~ob & ~sb`). It
    does NOT require the rest of the cascade to pass, so its cohort is dominated by
    name-days that no tier would have claimed even with the veto switched off.
  * `fresh_ticks_extension_replay.py` (#4546) measured the leg MIX at excluded ticks.

Neither answers "what does THIS leg, alone, cost or save the board?" — because a null on
the FAMILY is compatible with one leg helping and another hurting. That question needs
the SOLE-BLOCKER cohort: the name-days a tier WOULD have claimed if this one leg were
switched off, and no other veto leg fired.

THE PREDICATE, EXACTLY. engine/confluence_tiers.tier_stream (l.566-583) gates as

    if not not_topped[i]: continue
    if t1_fresh[i]: T1  elif t2_active[i]: T2  elif t3_active[i]: T3
    elif t4_active[i]: T4  else: continue
    elig[i] = True

so eligibility factorises exactly:  eligible == not_topped & tier_reachable, where
`tier_reachable = t1_fresh | t2_active | t3_active | t4_active` is computed WITHOUT
reference to the veto. Hence for leg L with siblings A, B:

    SOLE[L] := L & ~A & ~B & tier_reachable

is the cohort that (a) is blocked, (b) is blocked by L and nothing else, and (c) would
be ADMITTED the moment L is removed. Removing L admits SOLE[L] and nothing else, so the
same cohort is both the isolation slice and the forfeiture-pricing slice (G0.7: a veto's
removal is priced by BOTH what it stops costing and what it starts admitting).

The factorisation is not asserted — `equality_gate` re-derives `eligible` and
`not_topped` from the inline legs for EVERY name and compares cell-for-cell against
`tier_stream`. A non-zero mismatch is a defect in THIS instrument and is printed.

THE WARM-UP FAIL-OPEN (engine/confluence_tiers.py l.47-103, #4558). The 3D RSI-MACD
needs 232 daily bars; `macd_bear = m3n < s3n` and NaN < NaN is False, so below 232 bars
the leg reads "not bearish" rather than "not knowable". Note the DIRECTION carefully,
because it is the opposite of the obvious guess:

  * the leg cannot FIRE below 232 bars, so SOLE[macd_bear] is automatically clean;
  * what the fail-open contaminates is the ADMITTED CONTROL — rows admitted on two
    evaluated legs plus one that never ran. `section_2` measures that band directly and
    `deep_probe` asks what the leg WOULD have said there, off the spliced history.

Stats guards (house standins idiom, binding on every cohort): frozen-frame pinned
REPRO_ASOF; date-demeaned beside raw; per-name-first beside pooled; loser := excess vs
SPY < -3pp (STATED); thin cells print n and say thin; half-split robustness; per-leg
fire diagnostics so a leg that never fires is visible rather than silently null; every
truth test through bool()/== (memory: numpy-bool-is-true-deadens-a-feature-leg).

Re-run: python3 research/prophet_us_audit/veto_leg_isolation.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = str(Path(__file__).resolve().parents[2])
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "veto_leg_isolation_results.json")
os.chdir(REPO)
sys.path.insert(0, REPO)

from engine import confluence_tiers as ct                      # noqa: E402
from engine.confluence_tiers import (                          # noqa: E402
    BUY_RSI_MAX, CONF_W, EARLY_CROSS_BARS, FRESH_TICKS, OB, OS, RSI_LEN,
    _last_true_pos, _rsi_macd, _since, _stoch_rsi_kd, _tf_bars, _ticks_since_vec,
    _to_daily, _xup,
)
from engine.technicals import rsi                              # noqa: E402
from lib import store                                          # noqa: E402

# ---------------------------------------------------------------- constants --
REPRO_ASOF = "2026-07-31"     # frozen-replay pin — the SAME frame #4547 was authored
                              # against, so the two instruments are commensurable.
LOSER_PP = -3.0               # loser := excess vs SPY < -3pp at the horizon (STATED)
HORIZONS = (10, 21, 63)       # the brief's ladder; H=10 is primary (matches #4547)
H_PRIMARY = 10
THIN_N = 20                   # below this an n is called thin in its own row
LOOK = 126                    # #4547's section-2 window, replayed for cross-reading
MIN_HIST = 260                # universe floor (matches #4547 — same names, same frame)
BENCH = "SPY"
MACD3_WARMUP = ct.LEG_WARMUP_BARS["m3_s3"]      # 232 — measured, read from the engine
_GROUPS = ("breadth", "midcap_breadth", "smallcap_breadth")
_CASE_NAMES = ("RKLB", "ASTS")                  # operator exhibits — illustration only
RECEIPT_ASOF = "2026-08-03"   # last close carried by why_not_receipts_2026-08-05.json,
                              # so the exhibit is answered on its OWN date as well as on
                              # the frozen frame


# ------------------------------------------------------------------ helpers --
def _r(x, nd: int = 2):
    """Round, but never crash on a NaN/None/inf."""
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return round(f, nd) if np.isfinite(f) else None


def stats_block(ex_spy_pp, ex_dm_pp, tickers, *, thin_n: int = THIN_N) -> dict:
    """The house stat row: pooled raw + demeaned + per-name-first, with n and a thin
    flag. Lifted verbatim from label_grading_battery.stats_block so the cells in this
    file and in #4547 are read on identical arithmetic."""
    n = len(ex_spy_pp)
    if n == 0:
        return {"n": 0, "thin": True, "note": "no observations in this cell"}
    s = pd.Series(np.asarray(ex_spy_pp, dtype=float))
    d = pd.Series(np.asarray(ex_dm_pp, dtype=float))
    byname = pd.DataFrame({"t": list(tickers), "ex": s.to_numpy()}).groupby("t")["ex"].median()
    out = {
        "n": int(n),
        "names": int(byname.shape[0]),
        "loser_rate_pct": _r((s < LOSER_PP).mean() * 100, 1),
        "win_rate_pct": _r((s > 0).mean() * 100, 1),
        "median_excess_spy_pp": _r(s.median()),
        "median_excess_dm_pp": _r(d.median()),
        "per_name_first_median_pp": _r(byname.median()),
        "mean_excess_spy_pp": _r(s.mean()),
        "p25_pp": _r(s.quantile(0.25), 1),
        "p75_pp": _r(s.quantile(0.75), 1),
    }
    if n < thin_n:
        out["thin"] = True
        out["thin_note"] = f"THIN CELL — n={n} < {thin_n}; directional read only"
    return out


def half_split(dates, ex_spy_pp, ex_dm_pp, tickers) -> dict:
    """Robustness: split the cohort at its median event date and re-stat each half.
    A headline delta that only exists in one half is not a stable delta."""
    if len(dates) < 4:
        return {"note": "too few observations to half-split", "n": int(len(dates))}
    dser = pd.Series(pd.to_datetime(list(dates)))
    n_dates = int(dser.nunique())
    if n_dates < 2:
        return {"note": "UNRUNNABLE — all observations share a single date; a time "
                        "half-split cannot test this cohort",
                "n": int(len(dates)), "distinct_dates": n_dates}
    cut = dser.median()
    first = (dser <= cut).to_numpy()
    if first.all() or (~first).all():
        first = (dser < cut).to_numpy()
    if first.sum() == 0 or (~first).sum() == 0:
        return {"note": "UNRUNNABLE — dates too concentrated to form two non-empty halves",
                "n": int(len(dates)), "distinct_dates": n_dates}
    ex_spy_pp = np.asarray(ex_spy_pp, dtype=float)
    ex_dm_pp = np.asarray(ex_dm_pp, dtype=float)
    tk = np.asarray(list(tickers), dtype=object)
    a = stats_block(ex_spy_pp[first], ex_dm_pp[first], tk[first])
    b = stats_block(ex_spy_pp[~first], ex_dm_pp[~first], tk[~first])
    out = {"split_at": str(pd.Timestamp(cut).date()), "distinct_dates": n_dates,
           "first_half": a, "second_half": b}
    pa, pb = a.get("per_name_first_median_pp"), b.get("per_name_first_median_pp")
    if pa is not None and pb is not None:
        out["sign_flip_across_halves"] = bool((pa > 0) != (pb > 0))
        out["per_name_median_gap_pp"] = _r(abs(pa - pb))
    return out


def sector_concentration(tickers, sector_of: dict, top: int = 4) -> dict:
    """A cohort verdict carried by one sector is a sector call wearing a leg's clothes."""
    secs = pd.Series([sector_of.get(str(t), "unknown") for t in tickers])
    if secs.empty:
        return {"coverage_pct": 0.0}
    vc = secs.value_counts(normalize=True) * 100
    return {
        "coverage_pct": _r(float((secs != "unknown").mean() * 100), 1),
        "top_sectors_pct": {str(k): _r(v, 1) for k, v in vc.head(top).items()},
        "max_single_sector_pct": _r(vc.max(), 1),
    }


def _sector_map() -> dict:
    """ticker -> GICS sector off the constituents tables. Coverage is disclosed."""
    out: dict = {}
    for g in _GROUPS + ("russell_breadth",):
        p = Path(f"data/{g}/constituents.parquet")
        if not p.exists():
            continue
        try:
            m = pd.read_parquet(p)
        except (OSError, ValueError):
            continue
        if "sector" not in m.columns:
            continue
        for t, s in m["sector"].items():
            out.setdefault(str(t), str(s))
    return out


def gather(mask: np.ndarray, ex_spy: np.ndarray, ex_dm: np.ndarray,
           tickers: np.ndarray, dates: np.ndarray) -> tuple:
    """(ticker, date, excess_spy_pp, excess_dm_pp) for every True cell with a finite
    forward outcome."""
    ok = mask & np.isfinite(ex_spy) & np.isfinite(ex_dm)
    r, c = np.nonzero(ok)
    return (tickers[c], dates[r], ex_spy[ok] * 100.0, ex_dm[ok] * 100.0)


# --------------------------------------------------------------- the panels --
def load_universe() -> tuple[pd.DataFrame, dict[str, pd.Series], dict]:
    """``px`` — the three US closes caches EXACTLY as production reads them
    (scripts/build_stock_library.py l.681-712), truncated at REPRO_ASOF. Every leg is
    computed from this and nothing else: ``_tf_bars`` resamples on 2B/3B buckets whose
    PHASE is anchored on the series' first index date, so prepending history would shift
    every bucket boundary and de-align the legs from the gate they grade.

    ``deep`` — the same names spliced under with data/yahoo/<T>.parquet. Used ONLY by
    ``deep_probe``, whose whole subject is what a name with adequate history would have
    read; the phase shift is that probe's stated caveat, not a hidden assumption.
    """
    frames = [pd.read_parquet(f"data/{g}/_closes_cache.parquet") for g in _GROUPS]
    idx = sorted(set().union(*[set(f.index) for f in frames]))
    wide = pd.concat([f.reindex(idx) for f in frames], axis=1)
    wide = wide.loc[:, ~wide.columns.duplicated()]
    wide = wide.loc[wide.index <= pd.Timestamp(REPRO_ASOF)]
    px = wide.loc[:, wide.notna().sum() >= MIN_HIST]

    deep: dict[str, pd.Series] = {}
    deepened = 0
    ydir = Path("data/yahoo")
    for t in px.columns:
        base = px[t].dropna()
        p = ydir / f"{t}.parquet"
        if not p.exists():
            deep[t] = base
            continue
        try:
            y = pd.read_parquet(p)
        except (OSError, ValueError):
            deep[t] = base
            continue
        col = "close" if "close" in y.columns else "close_price"
        if col not in y.columns:
            deep[t] = base
            continue
        ys = y[col].dropna()
        ys.index = pd.to_datetime(ys.index)
        ys = ys[ys.index <= pd.Timestamp(REPRO_ASOF)]
        merged = base.combine_first(ys)          # cache wins on overlap
        if merged.notna().sum() > base.notna().sum():
            deepened += 1
        deep[t] = merged.dropna()
    prov = {
        "cache_names": int(wide.shape[1]),
        "universe_after_min_history": int(px.shape[1]),
        "min_history_sessions": MIN_HIST,
        "names_deepened_from_yahoo": int(deepened),
        "splice_scope": "deep_probe ONLY — every graded leg is computed on the unspliced "
                        "production cache series so its resample phase matches the gate",
        "frame": [str(pd.Timestamp(px.index[0]).date()),
                  str(pd.Timestamp(px.index[-1]).date())],
        "sessions": int(px.shape[0]),
    }
    return px, deep, prov


def _name_legs(c: pd.Series) -> dict:
    """Every leg of engine/confluence_tiers.tier_stream (l.472-559) replicated inline on
    ONE name's close series, vectorized per daily bar. Returns numpy arrays on ``c.index``.

    The replication is line-cited leg by leg and then PINNED by ``equality_gate`` — this
    docstring is not the evidence, the cell-for-cell comparison is.
    """
    di = c.index
    n = len(di)

    sm, smk = _tf_bars(c, 2)                                        # l.472
    m2, s2 = _rsi_macd(sm)
    h2 = m2 - s2
    mb2 = _xup(m2, s2)
    slope2 = h2 - h2.shift(1)
    btc = (-h2 / slope2)
    imm2 = ((h2 < 0) & (slope2 > 0) & (btc > 0) & (btc <= EARLY_CROSS_BARS)).fillna(False)

    ss3, sk3 = _tf_bars(c, 3)                                       # l.480
    k3, d3 = _stoch_rsi_kd(ss3)
    sb3 = _xup(k3, d3)
    recent3 = _since(sb3) <= CONF_W
    fromos3 = d3.rolling(CONF_W).min() < OS
    r14_3 = rsi(ss3, RSI_LEN)
    m3, s3 = _rsi_macd(ss3)
    mb3 = _xup(m3, s3)
    k2, d2 = _stoch_rsi_kd(sm)
    sb2 = _xup(k2, d2)
    recent2 = _since(sb2) <= CONF_W
    fromos2 = d2.rolling(CONF_W).min() < OS

    wk = c.resample("W-FRI").last().dropna()                        # l.493
    wm, ws = _rsi_macd(wk)
    wbull = (wm >= ws).shift(1)
    ma200 = c.rolling(200).mean()

    def td(s, kn, how="ffill", _di=di):
        return _to_daily(s, kn, _di, how)

    mb2_d = td(mb2.fillna(False), smk, "event")
    imm2_d = td(imm2.fillna(False), smk).fillna(False)
    m2_d, s2_d = td(m2, smk), td(s2, smk)
    mb3_d = td(mb3.fillna(False), sk3, "event")
    m3_d, s3_d = td(m3, sk3), td(s3, sk3)
    recent3_d = td(recent3.fillna(False), sk3).fillna(False)
    fromos3_d = td(fromos3.fillna(False), sk3).fillna(False)
    k3_d, d3_d = td(k3, sk3), td(d3, sk3)
    r14_d = td(r14_3, sk3)
    recent2_d = td(recent2.fillna(False), smk).fillna(False)
    fromos2_d = td(fromos2.fillna(False), smk).fillna(False)
    wbull_d = wbull.reindex(di, method="ffill").fillna(False).astype(bool)
    above200 = (c > ma200).fillna(False)

    confirm3 = (wbull_d | fromos3_d)
    confirm2 = (wbull_d | fromos2_d)
    rsi_ok = (r14_d < BUY_RSI_MAX).fillna(False)
    long_bias = ((m2_d >= s2_d) & (k3_d >= d3_d)).fillna(False)

    # ---- the three not-topped legs, verbatim from tier_stream l.519-524 -------------
    k3n, d3n = k3_d.to_numpy(), d3_d.to_numpy()
    m3n, s3n = m3_d.to_numpy(), s3_d.to_numpy()
    ob = (k3n >= OB) | (d3n >= OB)
    sb = k3n < d3n
    mb = m3n < s3n
    not_topped = ~(ob | sb | mb)

    mb3_np = mb3_d.fillna(False).to_numpy().astype(bool)            # l.527
    last_cross3 = _last_true_pos(mb3_np)
    t1_ticks = _ticks_since_vec(sk3, last_cross3, di, FRESH_TICKS)

    t2_buy = (mb2_d & recent3_d & confirm3 & rsi_ok).fillna(False).to_numpy().astype(bool)
    last_t2 = _last_true_pos(t2_buy)
    t2_ticks = _ticks_since_vec(smk, last_t2, di, FRESH_TICKS)

    imm2_np = imm2_d.to_numpy().astype(bool)
    recent3_np = recent3_d.to_numpy().astype(bool)
    confirm3_np = confirm3.fillna(False).to_numpy().astype(bool)
    confirm2_np = confirm2.fillna(False).to_numpy().astype(bool)
    rsi_ok_np = rsi_ok.to_numpy().astype(bool)
    recent2_np = recent2_d.to_numpy().astype(bool)
    above200_np = above200.to_numpy().astype(bool)
    long_bias_np = long_bias.to_numpy().astype(bool)

    t1_fresh = (last_cross3 >= 0) & (t1_ticks <= FRESH_TICKS)       # l.546
    t2_active = (last_t2 >= 0) & (t2_ticks <= FRESH_TICKS) & long_bias_np

    _t3_n = ct._t3_persist()                                        # l.551-557
    if _t3_n <= 1:
        imm2_persist_d = imm2_d.fillna(False)
    else:
        imm2_persist_tf = imm2.rolling(_t3_n, min_periods=_t3_n).min().fillna(False)
        imm2_persist_d = td(imm2_persist_tf.astype(float), smk).fillna(0).astype(bool)
    imm2_persist_np = imm2_persist_d.to_numpy().astype(bool)
    t3_active = imm2_persist_np & recent3_np & confirm3_np & rsi_ok_np
    t4_active = imm2_np & recent2_np & above200_np & confirm2_np & rsi_ok_np

    # THE FACTORISATION: tier_stream assigns a tier iff not_topped AND some tier is
    # reachable (l.566-583). `tier_reachable` is veto-free by construction, which is what
    # makes the counterfactual "switch leg L off" exactly computable.
    tier_reachable = t1_fresh | t2_active | t3_active | t4_active
    eligible = not_topped & tier_reachable

    return {
        "stoch_ob": ob, "stoch_bear": sb, "macd_bear": mb,
        "not_topped": not_topped, "tier_reachable": tier_reachable, "eligible": eligible,
        "t1_fresh": t1_fresh, "t2_active": t2_active,
        "t3_active": t3_active, "t4_active": t4_active,
        "bars": np.arange(1, n + 1, dtype=np.int32),
        "macd3_known": np.isfinite(m3n) & np.isfinite(s3n),
        "index": di,
    }


#: the legs whose fire counts are published — a leg missing here is invisible, so the
#: DEAD-LEG ALARM below cannot see it either.
DIAG_LEGS = ("stoch_ob", "stoch_bear", "macd_bear", "tier_reachable", "eligible",
             "t1_fresh", "t2_active", "t3_active", "t4_active")


def leg_diagnostics(panels: dict, legs: tuple[str, ...] = DIAG_LEGS) -> dict:
    """Per-leg fire counts + the DEAD-LEG ALARM.

    A leg that never fires is a defect in THIS instrument, never a finding about the
    tape — an all-False leg makes every cohort built on it print a plausible null. The
    alarm is REPORTED, not inferred, and it is a pure function of the panels so it can be
    tested against a deliberately-zeroed panel.
    """
    inrange = panels["has_px"].to_numpy()
    tot = max(int(inrange.sum()), 1)
    counts = {k: int(panels[k].to_numpy().sum()) for k in legs}
    return {
        "in_range_name_days": int(inrange.sum()),
        "fire_counts_name_days": counts,
        "fire_rate_pct_of_in_range": {k: _r(100.0 * v / tot, 2) for k, v in counts.items()},
        "names_firing_at_least_once": {
            k: int((panels[k].to_numpy().sum(axis=0) > 0).sum()) for k in legs},
        "dead_legs": [k for k, v in counts.items() if v == 0],
    }


def build_panels(px: pd.DataFrame) -> tuple[dict, dict]:
    """Lift every name's legs onto the universe index and run the equality gate."""
    idx = px.index
    n = len(idx)
    keys = ("stoch_ob", "stoch_bear", "macd_bear", "not_topped", "tier_reachable",
            "eligible", "t1_fresh", "t2_active", "t3_active", "t4_active",
            "macd3_known", "has_px")
    acc: dict[str, list[np.ndarray]] = {k: [] for k in keys}
    bars_acc: list[np.ndarray] = []
    cols: list[str] = []
    mism_nt = mism_el = cells = 0
    names_checked = names_empty = 0

    for t in px.columns:
        c = px[t].dropna()
        if len(c) < MIN_HIST:
            continue
        legs = _name_legs(c)
        di = legs["index"]

        # ---- equality gate, EVERY name (positive control for this instrument) -------
        st = ct.tier_stream(c)
        if st.empty:
            names_empty += 1
        else:
            names_checked += 1
            nt_p = st["not_topped"].reindex(di).fillna(False).to_numpy().astype(bool)
            el_p = st["eligible"].reindex(di).fillna(False).to_numpy().astype(bool)
            cells += len(di)
            mism_nt += int((nt_p != legs["not_topped"]).sum())
            mism_el += int((el_p != legs["eligible"]).sum())

        def onto(arr, fill=False, _di=di):
            s = pd.Series(arr, index=_di).reindex(idx)
            return s.fillna(fill).to_numpy()

        cols.append(t)
        for k in keys:
            if k == "has_px":
                acc[k].append(onto(np.ones(len(di), dtype=bool)))
            else:
                acc[k].append(onto(legs[k]))
        bars_acc.append(onto(legs["bars"], fill=0))

    panels = {k: pd.DataFrame(np.column_stack(v) if v else np.empty((n, 0)),
                              index=idx, columns=cols).astype(bool)
              for k, v in acc.items()}
    panels["bars"] = pd.DataFrame(np.column_stack(bars_acc) if bars_acc
                                  else np.empty((n, 0)), index=idx,
                                  columns=cols).astype(int)

    diag = leg_diagnostics(panels)
    diag["universe_names"] = len(cols)
    diag["sessions"] = n
    diag["equality_gate"] = {
        "basis": "inline legs vs engine.confluence_tiers.tier_stream, every name, "
                 "every in-range cell",
        "names_compared": names_checked,
        "names_tier_stream_empty": names_empty,
        "cells": cells,
        "not_topped_mismatches": mism_nt,
        "eligible_mismatches": mism_el,
        "status": "PASS" if (mism_nt == 0 and mism_el == 0) else "FAIL",
        "why_it_matters": "the sole-blocker predicate rests on eligible == not_topped & "
                          "tier_reachable; a mismatch here voids every cohort below",
    }
    return panels, diag


def _bench_forward(idx: pd.DatetimeIndex, h: int) -> pd.Series:
    """SPY forward return over h sessions on the universe index."""
    sp = store.read("yahoo", BENCH)
    col = "close" if (sp is not None and "close" in sp.columns) else "close_price"
    s = sp[col].dropna()
    s.index = pd.to_datetime(s.index)
    s = s[s.index <= pd.Timestamp(REPRO_ASOF)]
    s = s.reindex(idx).ffill()
    return s.shift(-h) / s - 1.0


# ------------------------------------------------------------- the sections --
def _cohorts(panels: dict) -> dict:
    """The sole-blocker cohorts + the admitted control + the fail-open cuts."""
    ob = panels["stoch_ob"].to_numpy()
    sb = panels["stoch_bear"].to_numpy()
    mb = panels["macd_bear"].to_numpy()
    reach = panels["tier_reachable"].to_numpy()
    elig = panels["eligible"].to_numpy()
    bars = panels["bars"].to_numpy()
    warm = bars >= MACD3_WARMUP

    return {
        "CONTROL:admitted": elig,
        "CONTROL:admitted_macd3_evaluated": elig & warm,
        "CONTROL:admitted_macd3_FAILOPEN": elig & ~warm,
        "SOLE:stoch_ob": ob & ~sb & ~mb & reach,
        "SOLE:stoch_bear": sb & ~ob & ~mb & reach,
        "SOLE:macd_bear": mb & ~ob & ~sb & reach,
        "SOLE:macd_bear_macd3_evaluated": mb & ~ob & ~sb & reach & warm,
        "BLOCKED:any_leg_reachable": (ob | sb | mb) & reach,
        "UNION:board_without_macd_bear": elig | (mb & ~ob & ~sb & reach),
    }


def section_isolation(px: pd.DataFrame, panels: dict, sector_of: dict) -> dict:
    """Per-leg isolation across the horizon ladder, on the full frozen frame."""
    idx = px.index
    n = len(idx)
    tickers = np.asarray(px.columns, dtype=object)
    dates = np.asarray(idx)
    coh = _cohorts(panels)

    res: dict = {
        "question": "for each not-topped leg separately, what does the cohort blocked "
                    "SOLELY by that leg do forward, against the cohort the gate admitted?",
        "predicate": "SOLE[L] = L & ~sibling_a & ~sibling_b & tier_reachable — blocked, "
                     "blocked by L alone, and admitted the moment L is removed",
        "windows": {
            "full_frame": "every name-day in the frozen frame carrying h forward "
                          "sessions (primary — the horizon ladder needs the depth)",
            "battery_window": f"the last {LOOK} sessions with full H={H_PRIMARY} forward "
                              "coverage — #4547 section_2's own window, replayed here so "
                              "the two instruments can be read cell against cell",
        },
        "by_window": {},
    }

    for wname in ("full_frame", "battery_window"):
        per_h: dict = {}
        for h in HORIZONS:
            hi = n - h
            if hi <= 0:
                per_h[f"H{h}"] = {"note": f"UNRUNNABLE — frame shorter than H={h}"}
                continue
            lo = 0 if wname == "full_frame" else max(0, (n - H_PRIMARY) - LOOK)
            if lo >= hi:
                per_h[f"H{h}"] = {
                    "note": f"UNRUNNABLE — no session in the {wname} window carries "
                            f"H={h} forward coverage",
                    "window_start_pos": int(lo), "h_coverage_end_pos": int(hi)}
                continue
            fwd = (px.shift(-h) / px - 1.0)
            uni_med = fwd.median(axis=1)
            spy_fwd = _bench_forward(idx, h)
            ex_spy = fwd.sub(spy_fwd, axis=0).to_numpy()[lo:hi]
            ex_dm = fwd.sub(uni_med, axis=0).to_numpy()[lo:hi]
            d_slice = dates[lo:hi]
            out: dict = {"window": [str(pd.Timestamp(idx[lo]).date()),
                                    str(pd.Timestamp(idx[hi - 1]).date())]}
            cells: dict = {}
            for cname, m in coh.items():
                mm = m[lo:hi]
                tk, dt, es, ed = gather(mm, ex_spy, ex_dm, tickers, d_slice)
                blk = stats_block(es, ed, tk)
                blk["cohort_cells_in_window"] = int(mm.sum())
                if blk.get("n", 0) > 0:
                    blk["sector_mix"] = sector_concentration(tk, sector_of)
                    if h == H_PRIMARY:
                        blk["half_split"] = half_split(dt, es, ed, tk)
                    # onset-only: the FIRST day of each contiguous run. The pooled cell
                    # double-counts a name that sits in a cohort for weeks.
                    prev = np.vstack([np.zeros((1, mm.shape[1]), dtype=bool), mm[:-1]])
                    tko, _d, eso, edo = gather(mm & ~prev, ex_spy, ex_dm, tickers, d_slice)
                    blk["onset_only"] = stats_block(eso, edo, tko)
                cells[cname] = blk
            # explicit vs-control deltas — the number the adjudication reads
            ctrl = cells.get("CONTROL:admitted", {})
            for cname, blk in cells.items():
                if cname.startswith("CONTROL") or blk.get("n", 0) == 0:
                    continue
                for key, tag in (("per_name_first_median_pp", "vs_control_per_name_pp"),
                                 ("median_excess_spy_pp", "vs_control_median_spy_pp"),
                                 ("loser_rate_pct", "vs_control_loser_pp")):
                    a, b = blk.get(key), ctrl.get(key)
                    blk[tag] = _r(a - b) if (a is not None and b is not None) else None
            out["cells"] = cells
            per_h[f"H{h}"] = out
        res["by_window"][wname] = per_h
    return res


def section_failopen(px: pd.DataFrame, panels: dict, deep: dict) -> dict:
    """The warm-up fail-open: how big is the band, whose rows sit in it, and — the
    load-bearing question — would the leg have vetoed there?"""
    bars = panels["bars"].to_numpy()
    inr = panels["has_px"].to_numpy()
    elig = panels["eligible"].to_numpy()
    mb = panels["macd_bear"].to_numpy()
    known = panels["macd3_known"].to_numpy()
    idx = px.index
    cols = list(panels["bars"].columns)

    band_now = inr & (bars >= ct.MIN_HISTORY) & (bars < MACD3_WARMUP)
    band_pre = inr & (bars >= ct.YOUNG_HISTORY_BARS) & (bars < MACD3_WARMUP)
    tot = int(inr.sum())

    res: dict = {
        "question": "the 3D RSI-MACD needs 232 daily bars and `macd_bear = m3n < s3n` "
                    "reads False on NaN — how many name-days ran with that leg "
                    "unevaluated, and is any measurement of the leg taken on a biased "
                    "subset because of it?",
        "engine_constants": {
            "macd3_warmup_bars": int(MACD3_WARMUP),
            "MIN_HISTORY_now": int(ct.MIN_HISTORY),
            "MIN_HISTORY_pre_4558": int(ct.YOUNG_HISTORY_BARS),
            "source": "engine/confluence_tiers.py l.87-103 (LEG_WARMUP_BARS, GATING_LEGS, "
                      "YOUNG_HISTORY_BARS) — read from the engine, not restated",
        },
        "direction_note": (
            "the fail-open cannot make the leg FIRE — below 232 bars both operands are "
            "NaN, so `macd_bear` is False. It therefore cannot contaminate the "
            "SOLE:macd_bear cohort. What it contaminates is the ADMITTED control: rows "
            "let through on two evaluated legs plus one that never ran."),
        "band_census": {
            "in_range_name_days": tot,
            "band_current_floor_159_to_231": {
                "name_days": int(band_now.sum()),
                "pct_of_in_range": _r(100.0 * band_now.sum() / max(tot, 1), 2),
                "names_touching_band": int((band_now.sum(axis=0) > 0).sum()),
            },
            "band_pre_4558_floor_200_to_231": {
                "name_days": int(band_pre.sum()),
                "pct_of_in_range": _r(100.0 * band_pre.sum() / max(tot, 1), 2),
                "names_touching_band": int((band_pre.sum(axis=0) > 0).sum()),
            },
        },
        "admissions_in_band": {
            "admitted_name_days_total": int(elig.sum()),
            "admitted_inside_band_current": int((elig & band_now).sum()),
            "admitted_inside_band_current_pct_of_admissions": _r(
                100.0 * (elig & band_now).sum() / max(int(elig.sum()), 1), 2),
            "admitted_inside_band_pre_4558": int((elig & band_pre).sum()),
            "admitted_inside_band_pre_4558_pct_of_admissions": _r(
                100.0 * (elig & band_pre).sum() / max(int(elig.sum()), 1), 2),
            "names_with_any_band_admission": int(((elig & band_now).sum(axis=0) > 0).sum()),
        },
        "sole_blocker_cohort_purity": {
            "sole_macd_bear_cells": int((mb & ~panels["stoch_ob"].to_numpy()
                                         & ~panels["stoch_bear"].to_numpy()
                                         & panels["tier_reachable"].to_numpy()).sum()),
            "of_which_below_warmup": int((mb & ~known).sum()),
            "note": "must be 0 — a leg that reads False on NaN cannot fire below its "
                    "warm-up. A non-zero here is an instrument defect.",
        },
        "prereg_study_contamination": {
            "study": "research/signal_engine/veto_leg_audit.py (the VETO_LEG_AUDIT prereg)",
            "verdict": "NOT CONTAMINATED",
            "evidence": "l.150-153 skips any fire whose k3/d3/m3/s3 are not all finite "
                        "(`if not all(np.isfinite(x) ...): continue`) BEFORE the dedup "
                        "anchor is advanced, so every graded fire had the 3D RSI-MACD "
                        "computable. The keep-rule failure was measured where the leg "
                        "actually evaluates.",
        },
    }

    # ---- deep probe: what WOULD the leg have said inside the band? -----------------
    probe = {
        "question": "on the admitted rows inside the fail-open band, what does the 3D "
                    "RSI-MACD read once the name is given adequate history?",
        "method": "recompute macd_bear on the yahoo-spliced series and read it on the "
                  "same calendar dates, restricted to rows where the leg is computable "
                  "on the deep series and NOT on the production cache series",
        "caveat": "_tf_bars resamples on 3B buckets anchored on the series' FIRST index "
                  "date, so the spliced series' bucket boundaries differ from "
                  "production's. This probe answers 'would an adequately-warmed name have "
                  "read bearish here', not 'production's own leg would have read X'.",
    }
    n_rows = would_veto = n_names = 0
    per_name_rows: list[int] = []
    probed_rows: set[int] = set()
    for j, t in enumerate(cols):
        cache_rows = np.nonzero(inr[:, j] & band_now[:, j] & elig[:, j])[0]
        if cache_rows.size == 0:
            continue
        dseries = deep.get(t)
        if dseries is None or len(dseries) <= int(panels["bars"].iloc[:, j].max()):
            continue
        try:
            ss3d, sk3d = _tf_bars(dseries, 3)
            m3d, s3d = _rsi_macd(ss3d)
            m3dd = _to_daily(m3d, sk3d, dseries.index)
            s3dd = _to_daily(s3d, sk3d, dseries.index)
        except Exception:                       # noqa: BLE001 — one bad series is not fatal
            continue
        mbd = (m3dd < s3dd)
        okd = np.isfinite(m3dd.to_numpy()) & np.isfinite(s3dd.to_numpy())
        mbd = pd.Series(np.where(okd, mbd.to_numpy(), np.nan), index=dseries.index)
        hit = mbd.reindex(idx[cache_rows])
        hit = hit[hit.notna()]
        if hit.empty:
            continue
        n_names += 1
        n_rows += int(hit.shape[0])
        per_name_rows.append(int(hit.shape[0]))
        would_veto += int(hit.astype(bool).sum())
        probed_rows.update(int(v) for v in np.nonzero(idx.isin(hit.index))[0])

    # POSITIVE CONTROL for the probe. The probe's rate is only interpretable against the
    # rate the leg posts where it genuinely evaluates, on the SAME kind of row: stoch
    # legs clean, a tier reachable.
    #
    # And then the DISCRIMINATING control. The band is a fixed slice of each cache
    # group's own history, so its rows are CALENDAR-CONCENTRATED — the large-cap sleeve
    # traverses it in one narrow window. A raw warm-row base rate therefore compares two
    # different tapes. The date-matched control restricts the warm rows to the same
    # sessions the probe drew from, which is the only comparison that isolates the
    # warm-up rather than the calendar.
    ob = panels["stoch_ob"].to_numpy()
    sb = panels["stoch_bear"].to_numpy()
    reach = panels["tier_reachable"].to_numpy()
    warm = inr & (bars >= MACD3_WARMUP)
    warm_clean = warm & ~ob & ~sb & reach
    warm_veto = int((warm_clean & mb).sum())
    warm_den = int(warm_clean.sum())

    same_rows = np.zeros(warm_clean.shape[0], dtype=bool)
    if probed_rows:
        same_rows[sorted(probed_rows)] = True
    wc_d = warm_clean & same_rows[:, None]
    wd_den, wd_veto = int(wc_d.sum()), int((wc_d & mb).sum())
    band_rate = (100.0 * would_veto / n_rows) if n_rows else None
    dm_rate = (100.0 * wd_veto / wd_den) if wd_den else None

    probe.update({
        "admitted_band_rows_probed": n_rows,
        "names_probed": n_names,
        "max_single_name_share_pct": _r(100.0 * max(per_name_rows) / n_rows, 1)
        if n_rows else None,
        "would_have_vetoed": would_veto,
        "would_have_vetoed_pct": _r(band_rate, 1),
        "positive_control_warm_rows": {
            "basis": "bars >= 232, stoch legs clean, tier reachable — the same row shape, "
                     "where the leg genuinely evaluates",
            "denominator": warm_den,
            "macd_bear_fires": warm_veto,
            "fire_rate_pct": _r(100.0 * warm_veto / warm_den, 1) if warm_den else None,
        },
        "date_matched_control": {
            "basis": "the same warm rows, restricted to the SESSIONS the probe drew from "
                     "— removes the band's calendar concentration from the comparison",
            "sessions": int(len(probed_rows)),
            "denominator": wd_den,
            "macd_bear_fires": wd_veto,
            "fire_rate_pct": _r(dm_rate, 1),
            "probe_minus_date_matched_pp": _r(band_rate - dm_rate)
            if (band_rate is not None and dm_rate is not None) else None,
        },
        "conservative_floor_band_admissions_that_would_have_been_vetoed": (
            int(round((min(band_rate, dm_rate) / 100.0)
                      * int((elig & band_now).sum())))
            if (band_rate is not None and dm_rate is not None) else None),
        "read": "the DIRECTION is what this probe supports — a large share of band "
                "admissions carried a 3D RSI-MACD that was in fact bearish. The exact "
                "share is not transferable: the phase caveat above and the band's "
                "calendar concentration both push on the level, which is why the "
                "date-matched control and a conservative floor are printed beside it.",
        "status": "RUN" if n_rows else "UNRUNNABLE — no admitted band row has deeper "
                                       "history available to probe with",
    })
    res["deep_probe"] = probe
    return res


def section_forfeiture(px: pd.DataFrame, panels: dict, iso: dict) -> dict:
    """G0.7 pricing: removing macd_bear is priced by BOTH what it stops costing and what
    it starts admitting. The added cohort IS SOLE:macd_bear (see the module docstring)."""
    coh = _cohorts(panels)
    elig = coh["CONTROL:admitted"]
    added = coh["SOLE:macd_bear"]
    n_sess = int(panels["has_px"].shape[0])
    sess_now = elig.sum(axis=1)
    sess_add = added.sum(axis=1)

    out: dict = {
        "question": "if macd_bear were removed, what does the board ADMIT that it does "
                    "not today — how many, and how does that added cohort grade?",
        "identity": "the added cohort is exactly SOLE:macd_bear — removing L admits "
                    "L & ~siblings & tier_reachable and nothing else",
        "volume": {
            "admitted_name_days_now": int(elig.sum()),
            "added_name_days": int(added.sum()),
            "widening_pct": _r(100.0 * added.sum() / max(int(elig.sum()), 1), 1),
            "admitted_per_session_mean_now": _r(float(sess_now.mean()), 2),
            "added_per_session_mean": _r(float(sess_add.mean()), 2),
            "sessions": n_sess,
            "names_added_at_least_once": int((added.sum(axis=0) > 0).sum()),
            "names_admitted_at_least_once": int((elig.sum(axis=0) > 0).sum()),
        },
        "grade_of_added_cohort": {},
        "grade_of_union_board": {},
        "read": {},
    }
    for h in HORIZONS:
        tag = f"H{h}"
        cells = (iso["by_window"]["full_frame"].get(tag, {}) or {}).get("cells", {})
        a = cells.get("SOLE:macd_bear", {})
        u = cells.get("UNION:board_without_macd_bear", {})
        c = cells.get("CONTROL:admitted", {})
        out["grade_of_added_cohort"][tag] = {
            k: a.get(k) for k in ("n", "names", "loser_rate_pct", "win_rate_pct",
                                  "median_excess_spy_pp", "median_excess_dm_pp",
                                  "per_name_first_median_pp", "vs_control_per_name_pp",
                                  "vs_control_loser_pp")}
        out["grade_of_union_board"][tag] = {
            "union": {k: u.get(k) for k in ("n", "names", "loser_rate_pct",
                                            "median_excess_spy_pp",
                                            "per_name_first_median_pp")},
            "control_today": {k: c.get(k) for k in ("n", "names", "loser_rate_pct",
                                                    "median_excess_spy_pp",
                                                    "per_name_first_median_pp")},
            "delta_union_minus_control": {
                "loser_rate_pp": _r((u.get("loser_rate_pct") or 0)
                                    - (c.get("loser_rate_pct") or 0), 1)
                if (u.get("loser_rate_pct") is not None
                    and c.get("loser_rate_pct") is not None) else None,
                "per_name_first_median_pp": _r((u.get("per_name_first_median_pp") or 0)
                                               - (c.get("per_name_first_median_pp") or 0))
                if (u.get("per_name_first_median_pp") is not None
                    and c.get("per_name_first_median_pp") is not None) else None,
            },
        }
    return out


def _case_row(s: pd.Series, asof: str) -> dict:
    """One name's veto/tier state on the last session at-or-before ``asof``."""
    s = s[s.index <= pd.Timestamp(asof)].dropna()
    if len(s) < MIN_HIST:
        return {"status": f"UNRUNNABLE — only {len(s)} closes at {asof}"}
    legs = _name_legs(s)
    i = len(s) - 1
    sole = bool(legs["macd_bear"][i] and not legs["stoch_ob"][i]
                and not legs["stoch_bear"][i])
    return {
        "asof": str(s.index[i].date()),
        "bars": int(legs["bars"][i]),
        "macd3_evaluated": bool(legs["macd3_known"][i]),
        "stoch_ob": bool(legs["stoch_ob"][i]),
        "stoch_bear": bool(legs["stoch_bear"][i]),
        "macd_bear": bool(legs["macd_bear"][i]),
        "not_topped": bool(legs["not_topped"][i]),
        "tier_reachable": bool(legs["tier_reachable"][i]),
        "eligible_today": bool(legs["eligible"][i]),
        "t1_fresh": bool(legs["t1_fresh"][i]),
        "t2_active": bool(legs["t2_active"][i]),
        "t3_active": bool(legs["t3_active"][i]),
        "t4_active": bool(legs["t4_active"][i]),
        "sole_blocked_by_macd_bear": bool(sole and legs["tier_reachable"][i]),
        "blocked_but_no_tier_reachable": bool(sole and not legs["tier_reachable"][i]),
        "days_in_SOLE_macd_bear_last_252": int(
            (legs["macd_bear"][-252:] & ~legs["stoch_ob"][-252:]
             & ~legs["stoch_bear"][-252:] & legs["tier_reachable"][-252:]).sum()),
        "days_blocked_by_macd_bear_alone_last_252": int(
            (legs["macd_bear"][-252:] & ~legs["stoch_ob"][-252:]
             & ~legs["stoch_bear"][-252:]).sum()),
    }


def section_case_receipts(panels: dict) -> dict:
    """The operator's exhibits. TWO NAMES ARE AN ILLUSTRATION, NOT EVIDENCE — this
    section exists to show what the cohort looks like on a named row, and its numbers
    never enter any verdict above."""
    res = {
        "status": "ILLUSTRATION ONLY — two names cannot carry a verdict and are not "
                  "used in any cohort statistic in this file",
        "receipt_source": "research/prophet_us_audit/why_not_receipts_2026-08-05.json "
                          "(#4554); that file's `blocking_leg` is the FIRST failing gate "
                          "in engine evaluation order, which is NOT the same claim as "
                          "'this name would be admitted if the leg were removed'. The "
                          "counterfactual is computed here rather than assumed.",
        "asof_dates": {"frozen_frame": REPRO_ASOF,
                       "receipt_frame": RECEIPT_ASOF,
                       "why_two": "the frozen frame is the graded universe's pin; the "
                                  "receipt frame is the operator exhibit's own last "
                                  "close, so the exhibit is answered on its own date"},
        "names": {},
    }
    for t in _CASE_NAMES:
        p = Path(f"data/yahoo/{t}.parquet")
        if not p.exists():
            res["names"][t] = {"status": f"UNRUNNABLE — data/yahoo/{t}.parquet absent"}
            continue
        try:
            y = pd.read_parquet(p)
        except (OSError, ValueError) as e:
            res["names"][t] = {"status": f"UNRUNNABLE — unreadable ({e})"}
            continue
        col = "close" if "close" in y.columns else "close_price"
        s = y[col].dropna()
        s.index = pd.to_datetime(s.index)
        res["names"][t] = {
            "at_frozen_frame": _case_row(s, REPRO_ASOF),
            "at_receipt_frame": _case_row(s, RECEIPT_ASOF),
            "note": "computed on data/yahoo — these names are curated extras outside the "
                    "three closes caches, so they are NOT in the graded universe above",
        }
    return res


def build_readout(res: dict) -> dict:
    """Derived from the tables above; no value is hand-entered."""
    ff = res["section_1_per_leg_isolation"]["by_window"]["full_frame"]
    out: dict = {"note": "derived from the tables above; no value is hand-entered"}
    per_leg: dict = {}
    for h in HORIZONS:
        cells = (ff.get(f"H{h}", {}) or {}).get("cells", {})
        row = {}
        for leg in ("SOLE:stoch_ob", "SOLE:stoch_bear", "SOLE:macd_bear"):
            c = cells.get(leg, {})
            row[leg] = {"n": c.get("n"), "names": c.get("names"),
                        "per_name_first_median_pp": c.get("per_name_first_median_pp"),
                        "vs_control_per_name_pp": c.get("vs_control_per_name_pp"),
                        "vs_control_loser_pp": c.get("vs_control_loser_pp"),
                        "thin": bool(c.get("thin", False))}
        ctl = cells.get("CONTROL:admitted", {})
        row["CONTROL:admitted"] = {"n": ctl.get("n"),
                                   "per_name_first_median_pp":
                                       ctl.get("per_name_first_median_pp"),
                                   "loser_rate_pct": ctl.get("loser_rate_pct")}
        per_leg[f"H{h}"] = row
    out["per_leg_vs_control"] = per_leg

    # a leg "separates" iff its sole-blocked cohort grades WORSE than the admitted
    # control (that is what a veto is for) on the primary horizon.
    prim = per_leg.get(f"H{H_PRIMARY}", {})
    out["separates_on_H10_per_name"] = {
        leg: (None if prim.get(leg, {}).get("vs_control_per_name_pp") is None
              else bool(prim[leg]["vs_control_per_name_pp"] < 0))
        for leg in ("SOLE:stoch_ob", "SOLE:stoch_bear", "SOLE:macd_bear")}
    out["sign_stable_across_horizons"] = {}
    for leg in ("SOLE:stoch_ob", "SOLE:stoch_bear", "SOLE:macd_bear"):
        vals = [per_leg[f"H{h}"][leg].get("vs_control_per_name_pp") for h in HORIZONS]
        vals = [v for v in vals if v is not None]
        out["sign_stable_across_horizons"][leg] = (
            None if len(vals) < 2 else bool(len({v > 0 for v in vals}) == 1))
    hs = ((ff.get(f"H{H_PRIMARY}", {}) or {}).get("cells", {})
          .get("SOLE:macd_bear", {}).get("half_split", {}))
    out["macd_bear_half_split_sign_flip"] = hs.get("sign_flip_across_halves")

    fo = res["section_2_failopen_and_contamination"]
    out["failopen"] = {
        "admitted_rows_in_band_pct": fo["admissions_in_band"][
            "admitted_inside_band_current_pct_of_admissions"],
        "sole_cohort_polluted_rows": fo["sole_blocker_cohort_purity"]["of_which_below_warmup"],
        "deep_probe_would_have_vetoed_pct": fo["deep_probe"].get("would_have_vetoed_pct"),
        "prereg_study_contaminated": fo["prereg_study_contamination"]["verdict"] != "NOT CONTAMINATED",
    }
    # the corrected read: naive SOLE:macd_bear vs the warm-up-restricted control
    cells = (ff.get(f"H{H_PRIMARY}", {}) or {}).get("cells", {})
    a = cells.get("SOLE:macd_bear", {})
    c_all = cells.get("CONTROL:admitted", {})
    c_ok = cells.get("CONTROL:admitted_macd3_evaluated", {})
    out["failopen_corrected_read_H10"] = {
        "sole_macd_bear_per_name_pp": a.get("per_name_first_median_pp"),
        "vs_control_all_pp": a.get("vs_control_per_name_pp"),
        "vs_control_macd3_evaluated_pp": (
            _r(a.get("per_name_first_median_pp") - c_ok.get("per_name_first_median_pp"))
            if (a.get("per_name_first_median_pp") is not None
                and c_ok.get("per_name_first_median_pp") is not None) else None),
        "control_all_n": c_all.get("n"),
        "control_macd3_evaluated_n": c_ok.get("n"),
        "control_shift_pp": (
            _r(c_ok.get("per_name_first_median_pp") - c_all.get("per_name_first_median_pp"))
            if (c_ok.get("per_name_first_median_pp") is not None
                and c_all.get("per_name_first_median_pp") is not None) else None),
    }
    out["forfeiture_H10"] = res["section_3_forfeiture_pricing"]["grade_of_added_cohort"].get(
        f"H{H_PRIMARY}")
    out["widening_pct"] = res["section_3_forfeiture_pricing"]["volume"]["widening_pct"]
    out["equality_gate"] = res["section_0_provenance"]["leg_diagnostics"]["equality_gate"]["status"]
    out["dead_legs"] = res["section_0_provenance"]["leg_diagnostics"]["dead_legs"]
    return out


def _agreement(diag: dict) -> dict:
    """Cross-instrument check against #4547's own leg census on the same frame.

    Both instruments replicate the same three legs from the same engine lines over the
    same universe and pin. If their fire counts disagree, one of them is measuring
    something else — and this file's whole argument would be about the wrong cohort.
    """
    p = Path(HERE) / "label_grading_battery_results.json"
    if not p.exists():
        return {"status": "UNRUNNABLE — label_grading_battery_results.json absent"}
    try:
        other = json.loads(p.read_text())
        od = other["section_2_veto_labels"]["leg_diagnostics"]
    except (OSError, ValueError, KeyError) as e:
        return {"status": f"UNRUNNABLE — {e}"}
    legs = ("stoch_ob", "stoch_bear", "macd_bear")
    mine = diag["fire_counts_name_days"]
    theirs = od.get("fire_counts_name_days", {})
    deltas = {k: int(mine.get(k, 0)) - int(theirs.get(k, 0)) for k in legs}
    return {
        "against": "research/prophet_us_audit/label_grading_battery_results.json (#4547)",
        "this_file": {k: int(mine.get(k, 0)) for k in legs},
        "that_file": {k: int(theirs.get(k, 0)) for k in legs},
        "deltas": deltas,
        "in_range_name_days_delta": (int(diag["in_range_name_days"])
                                     - int(od.get("in_range_name_days", 0))),
        "universe_names_delta": (int(diag["universe_names"])
                                 - int(od.get("universe_names", 0))),
        "status": "AGREE" if (all(v == 0 for v in deltas.values())
                              and diag["in_range_name_days"]
                              == od.get("in_range_name_days")) else "DISAGREE",
    }


def main() -> None:
    px, deep, prov = load_universe()
    print(f"universe {px.shape[1]} names x {px.shape[0]} sessions", flush=True)
    panels, diag = build_panels(px)
    print(f"equality gate: {diag['equality_gate']['status']} "
          f"(nt={diag['equality_gate']['not_topped_mismatches']}, "
          f"el={diag['equality_gate']['eligible_mismatches']} of "
          f"{diag['equality_gate']['cells']} cells)", flush=True)
    sector_of = _sector_map()

    res: dict = {
        "instrument": "W5.1 per-leg not-topped veto isolation (frozen-frame)",
        "charter": "research/prophet_us_audit/MACD_BEAR_RATIFICATION_PACKET.md",
        "scope": "MEASUREMENT ONLY — no gate/board/engine/config change follows from "
                 "this file; the W5 change stays sequenced behind G0.2 (five green "
                 "nightly miss-audits) AND operator ratification",
        "repro_asof": REPRO_ASOF,
        "loser_def_pp": LOSER_PP,
        "horizons": list(HORIZONS),
        "trial_ledger_family_status": "FIRST LOOK — data/trial_ledger.jsonl carries no "
                                      "prior veto-leg sweep family (1,366 rows checked)",
        "section_0_provenance": {"universe": prov, "leg_diagnostics": diag,
                                 "sector_map_names": len(sector_of),
                                 "cross_instrument_agreement": _agreement(diag)},
    }
    res["section_1_per_leg_isolation"] = section_isolation(px, panels, sector_of)
    res["section_2_failopen_and_contamination"] = section_failopen(px, panels, deep)
    res["section_3_forfeiture_pricing"] = section_forfeiture(
        px, panels, res["section_1_per_leg_isolation"])
    res["section_4_case_receipts"] = section_case_receipts(panels)
    res["readout"] = build_readout(res)

    with open(OUT, "w") as fh:
        json.dump(res, fh, indent=1, sort_keys=False, default=str)
    print(f"wrote {OUT}", flush=True)
    print(json.dumps(res["readout"], indent=1, default=str), flush=True)


if __name__ == "__main__":
    main()
