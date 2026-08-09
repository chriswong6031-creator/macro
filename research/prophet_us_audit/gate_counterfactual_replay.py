"""What would Prophet US's admission gate have claimed under four counterfactual gates?

MEASUREMENT ONLY. No engine, config, gate or board change follows from this file. Per house
epistemics the gauntlet is a PROMOTION gate, not a build gate — nothing here promotes
anything, and every null is printed rather than hidden.

THE QUESTION. The board missed a run of names (the precious-metals complex, the space
complex, a handful of young high-beta names). "The veto blocked them" and "the cascade never
reached them" are DIFFERENT failures with different repairs, and a family-level null on the
veto is compatible with one leg helping and another hurting. This instrument prices four
admission gates against the same tape and the same forward outcomes, so the cost of each is
a number rather than an anecdote.

THE FACTORISATION (the whole instrument rests on it). engine/confluence_tiers.tier_stream
(l.684-707) gates as

    if not not_topped[i]: continue
    if t1_fresh[i]: T1  elif t2_active[i]: T2  elif t3_active[i]: T3
    elif t4_active[i]: T4  else: continue
    elig[i] = True

so eligibility factorises EXACTLY as

    eligible == not_topped & tier_reachable,
    tier_reachable := t1_fresh | t2_active | t3_active | t4_active   (veto-free by construction)
    not_topped     := ~(stoch_ob | stoch_bear | macd_bear)           (l.641-646)

Because `tier_reachable` never reads a veto leg, "switch leg L off" is computable in closed
form: re-derive `not_topped` with L dropped and AND it against the SAME `tier_reachable`.
No monkeypatching, no forked math — the legs are rebuilt through the engine's own helpers
(`_tf_bars`, `_rsi_macd`, `_stoch_rsi_kd`, `_to_daily`, `_ticks_since_vec`, `_t3_persist`),
and the rebuild is PINNED cell-for-cell against `tier_stream` itself by `equality_gate`
before any variant is scored. A non-zero mismatch is a defect in THIS file, is printed, and
voids everything below it.

`fresh_ticks` is threaded the same way: `_ticks_since_vec` accepts-and-ignores its
`fresh_ticks` argument (engine l.537-539 — freshness is applied at the CALL SITE), so one
tick-age computation serves every fresh_ticks setting and FRESH4 is `t1_ticks <= 4` on the
identical array. That identity is pinned too, against `tier_stream(c, fresh_ticks=4)`.

THE VARIANTS.
  (a) LIVE                  the shipped gate, fresh_ticks=2, all three veto legs
  (b) NO_MACD               macd_bear dropped; stoch_ob + stoch_bear still veto
  (c) BASE_STATE_CONDITIONED  all three legs apply EXCEPT in a deep-base state (defined and
                            printed in the output), where they are waived
  (d) FRESH4                fresh_ticks 2 -> 4; vetoes unchanged
  (e) NO_STOCHBEAR_MACD     stoch_bear AND macd_bear dropped; stoch_ob kept — the pure
                            anti-extension guard alone

WHAT THE NUMBERS ARE AND ARE NOT. Every metric is STATED, both pooled and per-name-first (a
pooled cell is dominated by whichever names sit in a state for weeks; the per-name-first cell
gives every name one vote). Denominators are TIME-based, never outcome-based: an admission day
enters the scored denominator iff the frame carries H=10 forward sessions for it, which is a
function of the calendar alone and is applied identically to all five variants. The count of
admission days that CANNOT be scored is printed beside every cell rather than quietly dropped
(memory: resolution-conditioned-denominator-deletes-losers). Thin cells say thin. Every truth
test goes through bool().

Re-run: python3 research/prophet_us_audit/gate_counterfactual_replay.py
"""
from __future__ import annotations

import json
import os
import random
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

REPO = str(Path(__file__).resolve().parents[2])
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_JSON = os.path.join(HERE, "GATE_COUNTERFACTUAL_2026-08-07.json")
OUT_MD = os.path.join(HERE, "GATE_COUNTERFACTUAL_2026-08-07.md")
os.chdir(REPO)
sys.path.insert(0, REPO)

from engine import confluence_tiers as ct                      # noqa: E402
from engine.confluence_tiers import (                          # noqa: E402
    BUY_RSI_MAX, CONF_W, EARLY_CROSS_BARS, FRESH_TICKS, OB, OS, RSI_LEN,
    _last_true_pos, _rsi_macd, _since, _stoch_rsi_kd, _tf_bars, _ticks_since_vec,
    _to_daily, _xup,
)
from engine.technicals import rsi                              # noqa: E402

# ---------------------------------------------------------------- constants --
REPRO_ASOF = "2026-08-06"     # FROZEN replay pin. No wall-clock read anywhere in this file.
WINDOW_SESSIONS = 180         # the brief's window: the last 180 trading sessions at the pin
H = 10                        # forward horizon, in sessions
PRECISION_PP = 8.0            # precision := P(excess vs SPY >= +8pp) at H  (STATED)
LOSER_PP = -3.0               # loser     := P(excess vs SPY <= -3pp) at H  (STATED)
RUNUP_LOOK = 10               # lateness  := close vs min close of the 10 STRICTLY PRIOR sessions
DEEP_BASE_LOOK = 7            # deep-base: oversold anywhere in the last 7 sessions...
DEEP_BASE_OS = 20             #            ...meaning min(k3_d, d3_d) <= 20...
TURN_UP_LOOK = 5              #            ...AND close >= its own close 5 sessions ago
MIN_ROWS = 200                # universe floor for the fallback universe rule (the brief's)
THIN_N = 20                   # below this an n is called thin in its own row
MAX_NAMES = 1200              # runtime budget: deterministic every-Nth subset above this
EQ_GATE_NAMES = 30            # the brief's equality-gate sample (deterministic, seeded)
BENCH = "SPY"
MACD3_WARMUP = ct.LEG_WARMUP_BARS["m3_s3"]      # 232 — read from the engine, not restated

FOURTEEN = ("SBSW", "NEM", "HL", "FSM", "CDE", "GDX", "AG", "PAAS", "EXK",
            "SPCX", "RKLB", "ASTS", "MRNA", "CRCL")

VARIANTS = ("LIVE", "NO_MACD", "BASE_STATE_CONDITIONED", "FRESH4", "NO_STOCHBEAR_MACD")

DEFINITIONS = {
    "repro_asof": f"{REPRO_ASOF} — frozen; no wall-clock read, no network, no RNG outside a "
                  f"seeded deterministic sample",
    "window": f"the last {WINDOW_SESSIONS} trading sessions of the shared session calendar "
              f"ending at REPRO_ASOF",
    "admission": "a name-day on which tier_stream assigns a tier — i.e. `eligible` is True — "
                 "under the variant's gate. Identically: not_topped_VARIANT & tier_reachable",
    "tier_reachable": "t1_fresh | t2_active | t3_active | t4_active — computed WITHOUT any "
                      "reference to a veto leg (engine/confluence_tiers.py l.684-707)",
    "excess": f"excess := (name close-to-close return over the next {H} sessions) minus (SPY "
              f"return over the same {H} sessions), in percentage points",
    "precision": f"P(excess >= +{PRECISION_PP}pp | admission day) — STATED, inclusive bound",
    "loser_rate": f"P(excess <= {LOSER_PP}pp | admission day) — STATED, inclusive bound",
    "lateness_runup": f"100 * (close / min(close over the {RUNUP_LOOK} sessions STRICTLY prior) "
                      f"- 1), in percent, on the admission day. Higher = the gate arrived later "
                      f"into an already-extended move",
    "deep_base_state": f"min(k3_d, d3_d) <= {DEEP_BASE_OS} at ANY point in the last "
                       f"{DEEP_BASE_LOOK} sessions (3D StochRSI %K/%D mapped to daily, the "
                       f"engine's own k3_d/d3_d) AND close >= its own close {TURN_UP_LOOK} "
                       f"sessions ago (turning up). In that state variant (c) waives all three "
                       f"veto legs; outside it all three apply exactly as live",
    "scored_denominator": f"an admission day is SCORED iff the frame carries {H} forward "
                          f"sessions for it. That is a TIME truncation — a function of the "
                          f"calendar alone, identical across all five variants, and it cannot "
                          f"know which way a trade went. Admission days it excludes are counted "
                          f"and PRINTED as `unscorable_no_forward`, never silently dropped",
    "per_name_first": "the metric is computed inside each name, then the median is taken across "
                      "names — one vote per name. Printed BESIDE the pooled cell, which is "
                      "dominated by whichever names sit in a state for weeks",
    "thin": f"a cell with n < {THIN_N} is labelled thin and is a directional read only",
}


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


def _pct(num: int, den: int, nd: int = 1):
    return _r(100.0 * num / den, nd) if den else None


def _close_col(df: pd.DataFrame) -> str | None:
    for c in ("close", "close_price"):
        if c in df.columns:
            return c
    return None


def _read_series(path: Path) -> pd.Series | None:
    try:
        y = pd.read_parquet(path)
    except (OSError, ValueError):
        return None
    col = _close_col(y)
    if col is None:
        return None
    s = y[col].dropna()
    s.index = pd.to_datetime(s.index)
    s = s[s.index <= pd.Timestamp(REPRO_ASOF)]
    return s.sort_index()


# --------------------------------------------------------------- the panels --
def _name_legs(c: pd.Series) -> dict:
    """Every leg of engine/confluence_tiers.tier_stream (l.595-707) rebuilt on ONE name's
    close series through the ENGINE'S OWN helpers. Returns numpy arrays on ``c.index``.

    Nothing here is asserted to match — ``equality_gate`` compares it cell-for-cell against
    ``tier_stream`` itself. The tick-age arrays are returned RAW (not thresholded) because
    ``_ticks_since_vec`` ignores its ``fresh_ticks`` argument by design (engine l.537-539),
    so one computation serves every fresh_ticks setting.
    """
    di = c.index
    n = len(di)

    sm, smk = _tf_bars(c, 2)                                        # l.595
    m2, s2 = _rsi_macd(sm)
    h2 = m2 - s2
    mb2 = _xup(m2, s2)
    slope2 = h2 - h2.shift(1)
    btc = (-h2 / slope2)
    imm2 = ((h2 < 0) & (slope2 > 0) & (btc > 0) & (btc <= EARLY_CROSS_BARS)).fillna(False)

    ss3, sk3 = _tf_bars(c, 3)                                       # l.603
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

    wk = c.resample("W-FRI").last().dropna()                        # l.616
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

    # ---- the three veto legs, verbatim from tier_stream l.641-646 -------------------
    k3n, d3n = k3_d.to_numpy(), d3_d.to_numpy()
    m3n, s3n = m3_d.to_numpy(), s3_d.to_numpy()
    ob = (k3n >= OB) | (d3n >= OB)
    sb = k3n < d3n
    mb = m3n < s3n

    mb3_np = mb3_d.fillna(False).to_numpy().astype(bool)            # l.649
    last_cross3 = _last_true_pos(mb3_np)
    t1_ticks = _ticks_since_vec(sk3, last_cross3, di)

    t2_buy = (mb2_d & recent3_d & confirm3 & rsi_ok).fillna(False).to_numpy().astype(bool)
    last_t2 = _last_true_pos(t2_buy)
    t2_ticks = _ticks_since_vec(smk, last_t2, di)

    imm2_np = imm2_d.to_numpy().astype(bool)
    recent3_np = recent3_d.to_numpy().astype(bool)
    confirm3_np = confirm3.fillna(False).to_numpy().astype(bool)
    confirm2_np = confirm2.fillna(False).to_numpy().astype(bool)
    rsi_ok_np = rsi_ok.to_numpy().astype(bool)
    recent2_np = recent2_d.to_numpy().astype(bool)
    above200_np = above200.to_numpy().astype(bool)
    long_bias_np = long_bias.to_numpy().astype(bool)

    _t3_n = ct._t3_persist()                                        # l.673-680
    if _t3_n <= 1:
        imm2_persist_d = imm2_d.fillna(False)
    else:
        imm2_persist_tf = imm2.rolling(_t3_n, min_periods=_t3_n).min().fillna(False)
        imm2_persist_d = td(imm2_persist_tf.astype(float), smk).fillna(0).astype(bool)
    imm2_persist_np = imm2_persist_d.to_numpy().astype(bool)
    t3_active = imm2_persist_np & recent3_np & confirm3_np & rsi_ok_np
    t4_active = imm2_np & recent2_np & above200_np & confirm2_np & rsi_ok_np

    cn = c.to_numpy(dtype=float)
    prior_min = c.shift(1).rolling(RUNUP_LOOK).min().to_numpy(dtype=float)
    with np.errstate(invalid="ignore", divide="ignore"):
        runup = 100.0 * (cn / prior_min - 1.0)
    os_recent = (pd.Series(np.minimum(k3n, d3n), index=di)
                 .rolling(DEEP_BASE_LOOK, min_periods=1).min() <= DEEP_BASE_OS)
    turn_up = (c >= c.shift(TURN_UP_LOOK))
    deep_base = (os_recent & turn_up).fillna(False).to_numpy().astype(bool)

    return {
        "stoch_ob": ob, "stoch_bear": sb, "macd_bear": mb,
        "t3_active": t3_active, "t4_active": t4_active,
        "last_cross3": last_cross3, "t1_ticks": t1_ticks,
        "last_t2": last_t2, "t2_ticks": t2_ticks, "long_bias": long_bias_np,
        "deep_base": deep_base, "runup": runup,
        "bars": np.arange(1, n + 1, dtype=np.int32),
        "macd3_known": np.isfinite(m3n) & np.isfinite(s3n),
        "index": di,
    }


def _reachable(legs: dict, ft: int) -> np.ndarray:
    """tier_reachable at a given fresh_ticks. Veto-free by construction."""
    t1_fresh = (legs["last_cross3"] >= 0) & (legs["t1_ticks"] <= ft)
    t2_active = (legs["last_t2"] >= 0) & (legs["t2_ticks"] <= ft) & legs["long_bias"]
    return t1_fresh | t2_active | legs["t3_active"] | legs["t4_active"]


def _variant_masks(legs: dict) -> dict:
    """The five admission masks on the name's OWN index. Each is `not_topped_V & reachable_V`."""
    ob, sb, mb = legs["stoch_ob"], legs["stoch_bear"], legs["macd_bear"]
    reach2 = _reachable(legs, FRESH_TICKS)
    reach4 = _reachable(legs, 4)
    live_nt = ~(ob | sb | mb)
    return {
        "LIVE": live_nt & reach2,
        "NO_MACD": ~(ob | sb) & reach2,
        "BASE_STATE_CONDITIONED": (live_nt | legs["deep_base"]) & reach2,
        "FRESH4": live_nt & reach4,
        "NO_STOCHBEAR_MACD": ~ob & reach2,
        "_reach2": reach2,
        "_reach4": reach4,
    }


def equality_gate(series: dict[str, pd.Series], sample: list[str]) -> dict:
    """POSITIVE CONTROL. Re-derived LIVE eligibility vs `tier_stream` itself, cell-for-cell,
    on a deterministic sample — plus the same test at fresh_ticks=4, which is what licenses
    the FRESH4 variant to reuse one tick-age computation. A non-zero mismatch means this
    instrument is broken and every table below it is void."""
    cells = mism_live = mism_nt = mism_f4 = 0
    checked = empty = 0
    for t in sample:
        c = series[t]
        st = ct.tier_stream(c)
        st4 = ct.tier_stream(c, fresh_ticks=4)
        if st.empty or st4.empty:
            empty += 1
            continue
        legs = _name_legs(c)
        di = legs["index"]
        mv = _variant_masks(legs)
        el = st["eligible"].reindex(di).fillna(False).to_numpy().astype(bool)
        nt = st["not_topped"].reindex(di).fillna(False).to_numpy().astype(bool)
        el4 = st4["eligible"].reindex(di).fillna(False).to_numpy().astype(bool)
        checked += 1
        cells += len(di)
        mism_live += int((el != mv["LIVE"]).sum())
        mism_nt += int((nt != ~(legs["stoch_ob"] | legs["stoch_bear"] | legs["macd_bear"])).sum())
        mism_f4 += int((el4 != mv["FRESH4"]).sum())
    ok = bool(mism_live == 0 and mism_nt == 0 and mism_f4 == 0 and checked > 0)
    return {
        "basis": "re-derived legs vs engine.confluence_tiers.tier_stream, every in-range cell "
                 "of a deterministic sample of names (seeded, sorted universe)",
        "sample_size_requested": EQ_GATE_NAMES,
        "names_compared": checked,
        "names_tier_stream_empty": empty,
        "cells_compared": cells,
        "eligible_mismatches_LIVE": mism_live,
        "not_topped_mismatches": mism_nt,
        "eligible_mismatches_FRESH4": mism_f4,
        "status": "PASS" if ok else "FAIL",
        "why_it_matters": "every variant is `not_topped_V & tier_reachable`; a mismatch here "
                          "means the re-derivation is not the gate and no counterfactual below "
                          "is about the shipped board",
    }


# --------------------------------------------------------------- the metrics --
def stats_for(mask: np.ndarray, ex: np.ndarray, runup: np.ndarray,
              scorable: np.ndarray, tickers: np.ndarray) -> dict:
    """One variant's cell: pooled AND per-name-first, with every denominator printed.

    ``mask``     (S x N) admission days inside the window
    ``ex``       (S x N) excess vs SPY at H, in pp; NaN where the forward is not in the frame
    ``runup``    (S x N) pre-admission run-up in pct
    ``scorable`` (S,)    sessions that carry H forward sessions — a TIME truncation
    """
    n_sess, _ = mask.shape
    total = int(mask.sum())
    scored_mask = mask & scorable[:, None] & np.isfinite(ex)
    unscorable = total - int((mask & scorable[:, None]).sum())
    missing_fwd = int((mask & scorable[:, None] & ~np.isfinite(ex)).sum())
    rows, cols = np.nonzero(scored_mask)
    e = ex[scored_mask]
    tk = tickers[cols]
    n = int(e.size)

    out = {
        "admission_name_days": total,
        "sessions_in_window": n_sess,
        "admissions_per_session_mean": _r(total / n_sess, 2) if n_sess else None,
        "distinct_names_admitted": int((mask.sum(axis=0) > 0).sum()),
        "scored_admission_days": n,
        "unscorable_no_forward": unscorable,
        "scored_but_price_gap": missing_fwd,
        "scored_share_pct": _pct(n, total),
    }

    # per-name-first admissions/day: each admitted name's own admission-day count
    per_name_days = mask.sum(axis=0)
    admitted_days = per_name_days[per_name_days > 0]
    out["median_admission_days_per_admitted_name"] = (
        _r(float(np.median(admitted_days)), 1) if admitted_days.size else None)

    if n == 0:
        out.update({"precision_pct": None, "loser_rate_pct": None,
                    "median_runup_pct": None,
                    "per_name_first_precision_pct": None,
                    "per_name_first_loser_rate_pct": None,
                    "per_name_first_median_runup_pct": None,
                    "median_excess_pp": None, "names_scored": 0,
                    "thin": True,
                    "thin_note": "NO scored admission day in this cell — no forward-graded "
                                 "observation exists, the cell is null not zero"})
        return out

    hit = e >= PRECISION_PP
    lose = e <= LOSER_PP
    ru = runup[scored_mask]
    df = pd.DataFrame({"t": tk, "hit": hit, "lose": lose, "ex": e, "ru": ru})
    g = df.groupby("t")
    out.update({
        "names_scored": int(df["t"].nunique()),
        "precision_pct": _pct(int(hit.sum()), n),
        "loser_rate_pct": _pct(int(lose.sum()), n),
        "median_excess_pp": _r(float(np.median(e))),
        "median_runup_pct": _r(float(np.nanmedian(ru)), 1),
        "per_name_first_precision_pct": _r(float(g["hit"].mean().median() * 100), 1),
        "per_name_first_loser_rate_pct": _r(float(g["lose"].mean().median() * 100), 1),
        "per_name_first_median_excess_pp": _r(float(g["ex"].median().median())),
        "per_name_first_median_runup_pct": _r(float(g["ru"].median().median()), 1),
    })
    # lateness on ALL admission days, not only the scored ones — run-up is knowable on the
    # admission day itself, so restricting it to the scored subset would throw away signal.
    ru_all = runup[mask]
    ru_all = ru_all[np.isfinite(ru_all)]
    out["median_runup_pct_all_admissions"] = (
        _r(float(np.median(ru_all)), 1) if ru_all.size else None)
    if n < THIN_N:
        out["thin"] = True
        out["thin_note"] = f"THIN CELL — n={n} < {THIN_N}; directional read only"
    return out


# ------------------------------------------------------------- the 14 names --
def _fallback_series(t: str) -> tuple[pd.Series | None, str, str | None]:
    """Price ladder for a named exhibit: data/yahoo, then data/stocks, then the production
    closes caches. The SOURCE is reported with every row — two lineages are not one series,
    and a cache column that is mostly NaN is a COVERAGE fact, not a short listing history."""
    p = Path("data/yahoo") / f"{t}.parquet"
    if p.exists():
        s = _read_series(p)
        if s is not None and not s.empty:
            return s, "data/yahoo", None
    p = Path("data/stocks") / f"{t}.parquet"
    if p.exists():
        s = _read_series(p)
        if s is not None and not s.empty:
            return s, "data/stocks", None
    for g in ("breadth", "midcap_breadth", "smallcap_breadth", "russell_breadth"):
        p = Path(f"data/{g}/_closes_cache.parquet")
        if not p.exists():
            continue
        try:
            f = pd.read_parquet(p)
        except (OSError, ValueError):
            continue
        if t not in f.columns:
            continue
        col = f[t]
        s = col.dropna()
        s.index = pd.to_datetime(s.index)
        s = s[s.index <= pd.Timestamp(REPRO_ASOF)].sort_index()
        if not s.empty:
            note = (f"{len(s)} non-null closes inside a cache spanning {len(col)} sessions "
                    f"({col.index[0].date()} → {col.index[-1].date()}) — the column is "
                    f"populated only from {s.index[0].date()}, so the short history is this "
                    f"CACHE's coverage, not necessarily the name's listing history")
            return s, f"data/{g}/_closes_cache.parquet", note
    return None, "ABSENT", None


def name_table(win_idx: pd.DatetimeIndex, spy_fwd: pd.Series,
               in_universe: set[str]) -> dict:
    """The 14-name exhibit. Per name x variant: first admission in the window, or NONE plus the
    leg state on the most recent near-miss day. A name the engine cannot grade at all says so
    in those words — the young-name / missing-data wall is itself the finding."""
    rows: dict = {}
    for t in FOURTEEN:
        s, src, cov = _fallback_series(t)
        row: dict = {"source": src, "in_graded_universe": bool(t in in_universe)}
        if cov:
            row["source_coverage_note"] = cov
        if s is None:
            row["status"] = ("ABSENT — no close series on disk in data/yahoo, data/stocks or "
                             "any production closes cache; NOT gradable, and no network read "
                             "is permitted in this instrument")
            rows[t] = row
            continue
        row["bars"] = int(len(s))
        row["first_close"] = str(s.index[0].date())
        row["last_close"] = str(s.index[-1].date())
        row["macd_bear_evaluable_at_last_bar"] = bool(len(s) >= MACD3_WARMUP)
        if len(s) < ct.MIN_HISTORY:
            row["status"] = (f"UNDER MIN-HISTORY — {len(s)} daily bars < engine MIN_HISTORY "
                             f"{ct.MIN_HISTORY}; tier_stream returns an EMPTY frame, so NO "
                             f"variant can admit this name. The gate never saw it")
            rows[t] = row
            continue
        legs = _name_legs(s)
        di = legs["index"]
        mv = _variant_masks(legs)
        pos = pd.Series(np.arange(len(di)), index=di).reindex(win_idx).to_numpy()
        keep = np.isfinite(pos.astype(float))
        ipos = pos[keep].astype(int)
        wdates = win_idx[keep]
        row["sessions_in_window"] = int(keep.sum())

        # PER-DAY fail-open, not a whole-series length test: the 3D RSI-MACD needs
        # MACD3_WARMUP bars, so a name with enough bars TODAY can still have run most of the
        # window with `macd_bear` NaN -> False. Those days are LIVE == NO_MACD by construction.
        known_w = legs["macd3_known"][ipos]
        row["macd_bear_first_evaluable"] = (
            str(pd.Timestamp(di[int(np.argmax(legs["macd3_known"]))]).date())
            if bool(legs["macd3_known"].any()) else None)
        row["macd_bear_unevaluable_days_in_window"] = int((~known_w).sum())
        if int((~known_w).sum()) > 0:
            row["failopen_note"] = (
                f"`macd_bear` is UNEVALUABLE on {int((~known_w).sum())} of "
                f"{int(keep.sum())} window sessions for this name (needs {MACD3_WARMUP} bars; "
                f"NaN < NaN is False, so the leg cannot fire) — on those days LIVE and NO_MACD "
                f"are the SAME gate and any LIVE-vs-NO_MACD difference there is zero by "
                f"construction, not evidence about the leg")
        fwd = (s.shift(-H) / s - 1.0).reindex(wdates).to_numpy() * 100.0
        exc = fwd - spy_fwd.reindex(wdates).to_numpy() * 100.0
        row["status"] = "GRADED"
        row["variants"] = {}
        for v in VARIANTS:
            m = mv[v][ipos]
            reach = mv["_reach4" if v == "FRESH4" else "_reach2"][ipos]
            cell: dict = {"admission_days_in_window": int(m.sum()),
                          "admission_days_with_macd_bear_unevaluable": int((m & ~known_w).sum())}
            if bool(m.any()):
                first = int(np.argmax(m))
                cell["first_admission"] = str(pd.Timestamp(wdates[first]).date())
                cell["runup_at_first_admission_pct"] = _r(legs["runup"][ipos][first], 1)
                cell["macd_bear_evaluable_at_first_admission"] = bool(known_w[first])
                f_all = fwd[m]
                e_all = exc[m]
                fin = np.isfinite(f_all)
                cell["scored_admissions"] = int(fin.sum())
                cell["unscorable_no_forward"] = int((~fin).sum())
                if bool(fin.any()):
                    cell["max_fwd10_pct"] = _r(float(np.nanmax(f_all[fin])), 1)
                    cell["max_fwd10_excess_pp"] = _r(float(np.nanmax(e_all[np.isfinite(e_all)])), 1)
                    cell["median_fwd10_pct"] = _r(float(np.median(f_all[fin])), 1)
                else:
                    cell["max_fwd10_pct"] = None
                    cell["note"] = (f"every admission falls in the last {H} sessions of the "
                                    f"window — NO forward outcome exists yet; null, not zero")
            else:
                cell["first_admission"] = None
                nm = np.nonzero(reach)[0]
                if nm.size == 0:
                    cell["near_miss"] = ("NO tier reachable on any session in the window — this "
                                         "name was blocked by the CASCADE, not by a veto leg")
                else:
                    j = int(nm[-1])
                    cell["near_miss_day"] = str(pd.Timestamp(wdates[j]).date())
                    cell["near_miss_is_most_recent_reachable_day"] = True
                    cell["reachable_days_in_window"] = int(reach.sum())
                    fired = [k for k in ("stoch_ob", "stoch_bear", "macd_bear")
                             if bool(legs[k][ipos][j])]
                    cell["legs_firing_on_near_miss_day"] = fired
                    enforced = {"LIVE": ("stoch_ob", "stoch_bear", "macd_bear"),
                                "NO_MACD": ("stoch_ob", "stoch_bear"),
                                "BASE_STATE_CONDITIONED": ("stoch_ob", "stoch_bear", "macd_bear"),
                                "FRESH4": ("stoch_ob", "stoch_bear", "macd_bear"),
                                "NO_STOCHBEAR_MACD": ("stoch_ob",)}[v]
                    cell["blocking_legs_under_this_variant"] = [k for k in fired if k in enforced]
                    if v == "BASE_STATE_CONDITIONED":
                        cell["deep_base_on_near_miss_day"] = bool(legs["deep_base"][ipos][j])
            row["variants"][v] = cell
        # the name's own run, for scale — what the gate was deciding about
        cw = s.reindex(wdates).to_numpy(dtype=float)
        fin = np.isfinite(cw)
        if int(fin.sum()) > 1:
            row["window_return_pct"] = _r(100.0 * (cw[fin][-1] / cw[fin][0] - 1.0), 1)
            row["window_max_drawup_pct"] = _r(100.0 * (np.nanmax(cw[fin]) / cw[fin][0] - 1.0), 1)
        rows[t] = row
    return rows


# ------------------------------------------------------------------- driver --
def main() -> None:
    t_start = time.monotonic()

    # ---- universe rule, stated ------------------------------------------------------
    uni_note: dict = {}
    sp = json.loads(Path("site/factordata/us_standouts.json").read_text())
    u = sp.get("universe")
    uni_note["us_standouts_universe_field"] = {
        "value": u if isinstance(u, (int, float, str)) else f"<{type(u).__name__}>",
        "enumerable": bool(isinstance(u, (list, tuple, dict))),
        "verdict": "NOT enumerable — the field is an integer COUNT, not a ticker list, so the "
                   "brief's fallback rule applies",
        "board_as_of": sp.get("as_of"),
    }
    uni_note["universe_used"] = (f"every data/yahoo/*.parquet with >= {MIN_ROWS} daily closes at "
                                 f"REPRO_ASOF")

    series: dict[str, pd.Series] = {}
    files = sorted(Path("data/yahoo").glob("*.parquet"))
    short = 0
    for p in files:
        t = p.stem
        s = _read_series(p)
        if s is None or len(s) < MIN_ROWS:
            short += 1
            continue
        series[t] = s
    uni_note["yahoo_files"] = len(files)
    uni_note["dropped_under_min_rows"] = short
    uni_note["names_before_subset"] = len(series)

    tickers_all = sorted(series)
    subset_note = "NO SUBSET — the universe fits the runtime budget"
    if len(tickers_all) > MAX_NAMES:
        step = int(np.ceil(len(tickers_all) / MAX_NAMES))
        tickers_all = tickers_all[::step]
        subset_note = (f"SUBSET APPLIED — sorted tickers, every {step}th, "
                       f"{len(tickers_all)} names kept (deterministic)")
        series = {t: series[t] for t in tickers_all}
    uni_note["subset"] = subset_note
    uni_note["names_graded"] = len(tickers_all)
    print(f"universe {len(tickers_all)} names ({subset_note})", flush=True)

    # ---- the shared session calendar and the window ---------------------------------
    spy = _read_series(Path("data/yahoo") / f"{BENCH}.parquet")
    if spy is None or spy.empty:
        raise SystemExit(f"UNRUNNABLE — data/yahoo/{BENCH}.parquet absent; every excess "
                         f"number in this instrument is defined against it")
    cal = spy.index
    if len(cal) < WINDOW_SESSIONS + RUNUP_LOOK:
        raise SystemExit("UNRUNNABLE — benchmark calendar shorter than the window")
    win_idx = cal[-WINDOW_SESSIONS:]
    frame_idx = cal[-(WINDOW_SESSIONS + RUNUP_LOOK):]
    spy_w = spy.reindex(frame_idx)
    spy_fwd = (spy_w.shift(-H) / spy_w - 1.0)

    # ---- equality gate FIRST — nothing below is meaningful until it passes -----------
    rng = random.Random(20260807)
    sample = sorted(rng.sample(tickers_all, min(EQ_GATE_NAMES, len(tickers_all))))
    eq = equality_gate(series, sample)
    eq["sample"] = sample
    print(f"equality gate: {eq['status']} (live={eq['eligible_mismatches_LIVE']}, "
          f"nt={eq['not_topped_mismatches']}, f4={eq['eligible_mismatches_FRESH4']} of "
          f"{eq['cells_compared']} cells over {eq['names_compared']} names)", flush=True)
    if eq["status"] != "PASS":
        raise SystemExit("EQUALITY GATE FAILED — the instrument does not reproduce the gate; "
                         "no counterfactual below would be about the shipped board")

    # ---- build the panels over the window -------------------------------------------
    S, N = len(win_idx), len(tickers_all)
    masks = {v: np.zeros((S, N), dtype=bool) for v in VARIANTS}
    reach2_p = np.zeros((S, N), dtype=bool)
    known_p = np.zeros((S, N), dtype=bool)
    base_p = np.zeros((S, N), dtype=bool)
    inrange_p = np.zeros((S, N), dtype=bool)
    runup_p = np.full((S, N), np.nan)
    px_w = np.full((len(frame_idx), N), np.nan)
    warm_ok = np.zeros(N, dtype=bool)
    graded = 0
    for j, t in enumerate(tickers_all):
        c = series[t]
        px_w[:, j] = c.reindex(frame_idx).to_numpy(dtype=float)
        if len(c) < ct.MIN_HISTORY:
            continue
        legs = _name_legs(c)
        di = legs["index"]
        graded += 1
        warm_ok[j] = bool(len(c) >= MACD3_WARMUP)
        mv = _variant_masks(legs)
        pos = pd.Series(np.arange(len(di)), index=di).reindex(win_idx)
        ok = pos.notna().to_numpy()
        ip = pos.to_numpy()[ok].astype(int)
        for v in VARIANTS:
            masks[v][ok, j] = mv[v][ip]
        reach2_p[ok, j] = mv["_reach2"][ip]
        known_p[ok, j] = legs["macd3_known"][ip]
        base_p[ok, j] = legs["deep_base"][ip]
        inrange_p[ok, j] = True
        runup_p[ok, j] = legs["runup"][ip]
        if (j + 1) % 100 == 0:
            print(f"  legs {j + 1}/{N} ({time.monotonic() - t_start:.0f}s)", flush=True)

    # ---- forward outcomes ------------------------------------------------------------
    fwd = np.full_like(px_w, np.nan)
    fwd[:-H] = px_w[H:] / px_w[:-H] - 1.0
    spy_f = spy_fwd.to_numpy(dtype=float)
    ex_full = (fwd - spy_f[:, None]) * 100.0
    ex_w = ex_full[-WINDOW_SESSIONS:]
    scorable = np.isfinite(spy_f[-WINDOW_SESSIONS:])
    tickers_np = np.asarray(tickers_all, dtype=object)

    per_variant = {v: stats_for(masks[v], ex_w, runup_p, scorable, tickers_np)
                   for v in VARIANTS}
    live = per_variant["LIVE"]
    for v in VARIANTS:
        if v == "LIVE":
            continue
        b = per_variant[v]
        for key, tag in (("precision_pct", "vs_live_precision_pp"),
                         ("loser_rate_pct", "vs_live_loser_pp"),
                         ("per_name_first_precision_pct", "vs_live_per_name_precision_pp"),
                         ("median_runup_pct_all_admissions", "vs_live_runup_pp"),
                         ("admissions_per_session_mean", "vs_live_admissions_per_session")):
            a, c0 = b.get(key), live.get(key)
            b[tag] = _r(a - c0) if (a is not None and c0 is not None) else None
        b["added_name_days_vs_live"] = int((masks[v] & ~masks["LIVE"]).sum())
        b["removed_name_days_vs_live"] = int((masks["LIVE"] & ~masks[v]).sum())
        b["names_added_vs_live"] = int((((masks[v] & ~masks["LIVE"]).sum(axis=0) > 0)).sum())

    inr = int(inrange_p.sum())
    unev = int((inrange_p & ~known_p).sum())
    diag = {
        "names_graded_by_the_engine": graded,
        "names_in_panel": N,
        "names_below_MIN_HISTORY": int(N - graded),
        "in_range_name_days_in_window": inr,
        "names_with_macd_bear_evaluable_at_last_bar": int(warm_ok.sum()),
        "macd_bear_UNEVALUABLE_name_days_in_window": unev,
        "macd_bear_unevaluable_pct_of_in_range": _pct(unev, inr, 2),
        "names_with_any_unevaluable_day_in_window": int(
            ((inrange_p & ~known_p).sum(axis=0) > 0).sum()),
        "LIVE_admissions_on_macd_bear_unevaluable_days": int((masks["LIVE"] & ~known_p).sum()),
        "failopen_note": f"WHOLE-SERIES length is NOT the test: the 3D RSI-MACD needs "
                         f"{MACD3_WARMUP} daily bars, so a name with enough bars at the pin can "
                         f"still have run most of the window with `macd_bear` NaN. NaN < NaN is "
                         f"False, so the leg cannot FIRE there — on those name-days LIVE and "
                         f"NO_MACD are the SAME gate by construction and contribute zero to the "
                         f"NO_MACD delta, which is therefore carried entirely by the warm days",
        "deep_base_name_days_in_window": int((inrange_p & base_p).sum()),
        "deep_base_pct_of_in_range": _pct(int((inrange_p & base_p).sum()), inr, 1),
        "reachable_name_days_in_window": int(reach2_p.sum()),
        "veto_blocked_reachable_name_days": int((reach2_p & ~masks["LIVE"]).sum()),
        "sessions_in_window": S,
        "window": [str(pd.Timestamp(win_idx[0]).date()), str(pd.Timestamp(win_idx[-1]).date())],
        "scorable_sessions": int(scorable.sum()),
        "unscorable_tail_sessions": int((~scorable).sum()),
        "dead_variants": [v for v in VARIANTS if int(masks[v].sum()) == 0],
    }
    # STRUCTURAL CONTROL. Every variant relaxes a veto or widens freshness, so each must be a
    # strict SUPERSET of LIVE. A non-empty "removed" set means a variant mask is mis-built —
    # reported as a check with a verdict, never left as a number nobody reads.
    removed = {v: int((masks["LIVE"] & ~masks[v]).sum()) for v in VARIANTS}
    diag["superset_of_live_check"] = {
        "basis": "every variant either drops a veto leg or raises fresh_ticks, so LIVE's "
                 "admissions must all survive in it",
        "live_admission_days_lost_per_variant": removed,
        "status": "PASS" if all(v == 0 for v in removed.values()) else "FAIL",
    }

    res = {
        "instrument": "Prophet US admission-gate counterfactual replay (frozen-frame)",
        "scope": "MEASUREMENT ONLY — no engine, config, gate or board change follows from this "
                 "file. Display tier under house epistemics; a null here blocks nothing",
        "repro_asof": REPRO_ASOF,
        "definitions": DEFINITIONS,
        "variant_definitions": {
            "LIVE": "the shipped gate: fresh_ticks=2, not_topped = ~(stoch_ob|stoch_bear|macd_bear)",
            "NO_MACD": "macd_bear dropped; stoch_ob and stoch_bear still veto",
            "BASE_STATE_CONDITIONED": "all three legs apply EXCEPT in the deep-base state "
                                      "(see definitions.deep_base_state), where all three are waived",
            "FRESH4": "fresh_ticks 2 -> 4 (tier_stream's own knob); vetoes unchanged",
            "NO_STOCHBEAR_MACD": "stoch_bear AND macd_bear dropped; stoch_ob kept — the pure "
                                 "anti-extension guard alone",
        },
        "universe": uni_note,
        "equality_gate": eq,
        "diagnostics": diag,
        "section_1_variant_metrics": per_variant,
        "section_2_fourteen_names": name_table(win_idx, spy_fwd, set(tickers_all)),
        "runtime_seconds": None,
    }
    res["section_2_fourteen_names_note"] = (
        "the 14 names are an EXHIBIT, not a cohort — 14 names cannot carry a verdict and none "
        "of their numbers enters section 1. Names outside the graded universe are priced off "
        "the source printed on their row; two lineages are not one series")
    res["runtime_seconds"] = _r(time.monotonic() - t_start, 1)

    Path(OUT_JSON).write_text(json.dumps(res, indent=1, default=str))
    Path(OUT_MD).write_text(render_md(res))
    print(f"wrote {OUT_JSON}", flush=True)
    print(f"wrote {OUT_MD}", flush=True)
    print(f"runtime {res['runtime_seconds']}s", flush=True)


# ------------------------------------------------------------------ the .md --
def _f(x, dash: str = "null"):
    return dash if x is None else (f"{x}" if not isinstance(x, float) else f"{x:g}")


def render_md(r: dict) -> str:
    """The report is GENERATED from the JSON above — no value is hand-entered."""
    d, dg, eq = r["definitions"], r["diagnostics"], r["equality_gate"]
    L: list[str] = []
    A = L.append
    A("# Prophet US — admission-gate counterfactual replay")
    A("")
    A(f"**{r['scope']}**  ")
    A(f"Frozen pin `REPRO_ASOF = {r['repro_asof']}` · window "
      f"`{dg['window'][0]} → {dg['window'][1]}` ({dg['sessions_in_window']} sessions) · "
      f"runtime {r['runtime_seconds']}s · generated from "
      f"`research/prophet_us_audit/gate_counterfactual_replay.py`")
    A("")
    A("## 0. Equality gate (this instrument vs the engine)")
    A("")
    A(f"`{eq['status']}` — {eq['cells_compared']:,} cells over {eq['names_compared']} names "
      f"(deterministic seeded sample). LIVE eligible mismatches **{eq['eligible_mismatches_LIVE']}**, "
      f"not_topped mismatches **{eq['not_topped_mismatches']}**, FRESH4 eligible mismatches "
      f"**{eq['eligible_mismatches_FRESH4']}**. Non-zero would mean the re-derivation is not the "
      f"gate and every table below is void.")
    A("")
    A("## 1. Definitions (all stated, none inferred)")
    A("")
    for k in ("window", "admission", "tier_reachable", "excess", "precision", "loser_rate",
              "lateness_runup", "deep_base_state", "scored_denominator", "per_name_first",
              "thin"):
        A(f"- **{k}** — {d[k]}")
    A("")
    A("**Variants.** " + " · ".join(f"`{k}` {v}" for k, v in r["variant_definitions"].items()))
    A("")
    u = r["universe"]
    A(f"**Universe.** `site/factordata/us_standouts.json`'s `universe` field is "
      f"`{u['us_standouts_universe_field']['value']}` — {u['us_standouts_universe_field']['verdict']}. "
      f"Used instead: {u['universe_used']} → {u['names_before_subset']} of {u['yahoo_files']} files "
      f"({u['dropped_under_min_rows']} dropped). {u['subset']}. Board as-of on that file: "
      f"{u['us_standouts_universe_field']['board_as_of']}.")
    A("")
    A(f"**Coverage nulls (printed, not hidden).** {dg['names_below_MIN_HISTORY']} of "
      f"{dg['names_in_panel']} names sit below the engine's MIN_HISTORY and are gradable by NO "
      f"variant. `macd_bear` is UNEVALUABLE on {dg['macd_bear_UNEVALUABLE_name_days_in_window']:,} "
      f"of {dg['in_range_name_days_in_window']:,} in-range name-days "
      f"({_f(dg['macd_bear_unevaluable_pct_of_in_range'])}%, across "
      f"{dg['names_with_any_unevaluable_day_in_window']} names) — "
      f"{dg['LIVE_admissions_on_macd_bear_unevaluable_days']} LIVE admissions sit on such a day. "
      f"{dg['failopen_note']}. The deep-base state of variant (c) holds on "
      f"{dg['deep_base_name_days_in_window']:,} in-range name-days "
      f"({_f(dg['deep_base_pct_of_in_range'])}%), so that waiver is wide, not surgical. "
      f"The last {dg['unscorable_tail_sessions']} sessions of the window carry no H={H} forward, "
      f"so admissions on them are counted and reported as `unscorable`, never dropped from a "
      f"numerator alone.")
    A("")
    A(f"**Gate pressure.** {dg['reachable_name_days_in_window']:,} name-days reached a tier in "
      f"the window; {dg['veto_blocked_reachable_name_days']:,} of them "
      f"({_f(_pct(dg['veto_blocked_reachable_name_days'], dg['reachable_name_days_in_window']))}%) "
      f"were vetoed by the live not-topped triple. Structural control — every variant must be a "
      f"superset of LIVE: `{dg['superset_of_live_check']['status']}` "
      f"({dg['superset_of_live_check']['live_admission_days_lost_per_variant']}).")
    A("")
    A("## 2. Variant metrics")
    A("")
    A("Pooled cells. `adm/day` = admission name-days per session; `prec` = P(excess ≥ "
      f"+{PRECISION_PP:g}pp); `loser` = P(excess ≤ {LOSER_PP:g}pp); `run-up` = median lateness "
      "over ALL admission days; `names` = distinct names admitted; `unscored` = admission days "
      "with no H=10 forward in the frame.")
    A("")
    A("| variant | adm/day | names | adm-days | scored | unscored | prec % | loser % | "
      "median excess pp | run-up % |")
    A("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for v in VARIANTS:
        c = r["section_1_variant_metrics"][v]
        A(f"| `{v}` | {_f(c['admissions_per_session_mean'])} | {c['distinct_names_admitted']} | "
          f"{c['admission_name_days']} | {c['scored_admission_days']} | "
          f"{c['unscorable_no_forward']} | {_f(c['precision_pct'])} | {_f(c['loser_rate_pct'])} | "
          f"{_f(c['median_excess_pp'])} | {_f(c['median_runup_pct_all_admissions'])} |")
    A("")
    A("Per-name-first cells (each name votes once) and the delta against LIVE.")
    A("")
    A("| variant | names scored | prec % (pnf) | loser % (pnf) | median excess pp (pnf) | "
      "run-up % (pnf) | med adm-days/name | Δ prec pp | Δ loser pp | +name-days | −name-days | "
      "+names | thin |")
    A("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    for v in VARIANTS:
        c = r["section_1_variant_metrics"][v]
        A(f"| `{v}` | {_f(c.get('names_scored'))} | {_f(c['per_name_first_precision_pct'])} | "
          f"{_f(c['per_name_first_loser_rate_pct'])} | "
          f"{_f(c.get('per_name_first_median_excess_pp'))} | "
          f"{_f(c['per_name_first_median_runup_pct'])} | "
          f"{_f(c['median_admission_days_per_admitted_name'])} | "
          f"{_f(c.get('vs_live_precision_pp'), '—')} | {_f(c.get('vs_live_loser_pp'), '—')} | "
          f"{_f(c.get('added_name_days_vs_live'), '—')} | "
          f"{_f(c.get('removed_name_days_vs_live'), '—')} | "
          f"{_f(c.get('names_added_vs_live'), '—')} | "
          f"{'THIN' if c.get('thin') else ''} |")
    A("")
    if dg["dead_variants"]:
        A(f"**DEAD-VARIANT ALARM** — {dg['dead_variants']} admitted nothing at all. A variant "
          f"that never fires is a defect in this instrument, not a finding about the tape.")
        A("")
    A("## 3. The 14-name exhibit")
    A("")
    A(r["section_2_fourteen_names_note"][0].upper() + r["section_2_fourteen_names_note"][1:] + ".")
    A("")
    A("First admission date inside the window per name × variant. `—` = no admission under that "
      "variant.")
    A("")
    A("| name | source | bars | status | LIVE | NO_MACD | BASE_STATE | FRESH4 | NO_SB_MACD |")
    A("|---|---|---:|---|---|---|---|---|---|")
    nt = r["section_2_fourteen_names"]
    for t in FOURTEEN:
        row = nt[t]
        st = row["status"]
        short = ("ABSENT" if st.startswith("ABSENT") else
                 "UNDER MIN-HISTORY" if st.startswith("UNDER") else "graded")
        cells = []
        for v in VARIANTS:
            if short != "graded":
                cells.append("n/a")
                continue
            fa = row["variants"][v].get("first_admission")
            cells.append(fa if fa else "—")
        A(f"| **{t}** | {row['source']} | {_f(row.get('bars'), '—')} | {short} | "
          + " | ".join(cells) + " |")
    A("")
    A("**Names the gate could never see.**")
    for t in FOURTEEN:
        row = nt[t]
        if row["status"].startswith("ABSENT") or row["status"].startswith("UNDER"):
            A(f"- `{t}` — {row['status']}."
              + (f" Source coverage: {row['source_coverage_note']}."
                 if row.get("source_coverage_note") else ""))
    A("")
    fo = [t for t in FOURTEEN
          if nt[t].get("macd_bear_unevaluable_days_in_window", 0) > 0]
    A("**Where `macd_bear` was not even evaluable.** On these exhibit rows LIVE and NO_MACD are "
      "the SAME gate for part of the window, so a LIVE-vs-NO_MACD difference there is zero by "
      "construction rather than evidence about the leg.")
    if fo:
        for t in fo:
            row = nt[t]
            A(f"- `{t}` — unevaluable on {row['macd_bear_unevaluable_days_in_window']} of "
              f"{row['sessions_in_window']} window sessions; first evaluable "
              f"{_f(row.get('macd_bear_first_evaluable'), 'NEVER')} "
              f"(needs {MACD3_WARMUP} bars, series starts {row['first_close']}).")
    else:
        A("- None — every gradable exhibit name carried an evaluable 3D RSI-MACD across the "
          "whole window.")
    A("")
    A("**Admitted cells — what the name actually did.** `max fwd10` = the best 10-session "
      "forward return from any admission day under that variant; `excess` is against SPY.")
    A("")
    A("| name | variant | first admission | adm-days | run-up at first % | max fwd10 % | "
      "max fwd10 excess pp | unscored | macd_bear live at 1st adm? |")
    A("|---|---|---|---:|---:|---:|---:|---:|---|")
    any_adm = False
    for t in FOURTEEN:
        row = nt[t]
        if row["status"] != "GRADED":
            continue
        for v in VARIANTS:
            c = row["variants"][v]
            if not c.get("first_admission"):
                continue
            any_adm = True
            A(f"| {t} | `{v}` | {c['first_admission']} | {c['admission_days_in_window']} | "
              f"{_f(c.get('runup_at_first_admission_pct'))} | {_f(c.get('max_fwd10_pct'))} | "
              f"{_f(c.get('max_fwd10_excess_pp'))} | {_f(c.get('unscorable_no_forward'))} | "
              f"{'yes' if c.get('macd_bear_evaluable_at_first_admission') else 'NO (fail-open)'} |")
    if not any_adm:
        A("| — | — | NO admission under ANY variant for any gradable exhibit name | | | | | |")
    A("")
    A("**Near-miss attribution for the `—` cells** — the most recent session in the window on "
      "which a tier was reachable, and the veto legs firing there.")
    A("")
    near_lines = 0
    for t in FOURTEEN:
        row = nt[t]
        if row["status"] != "GRADED":
            continue
        parts = []
        for v in VARIANTS:
            c = row["variants"][v]
            if c.get("first_admission"):
                continue
            if "near_miss" in c:
                parts.append(f"`{v}` {c['near_miss']}")
            else:
                fired = ",".join(c.get("legs_firing_on_near_miss_day") or []) or "none"
                blk = ",".join(c.get("blocking_legs_under_this_variant") or []) or "none"
                parts.append(f"`{v}` last reachable {c['near_miss_day']} "
                             f"({c['reachable_days_in_window']} reachable days); legs firing: "
                             f"{fired}; still blocking under this variant: {blk}")
        if parts:
            near_lines += 1
            A(f"- **{t}** ({_f(row.get('window_return_pct'))}% over the window, max draw-up "
              f"{_f(row.get('window_max_drawup_pct'))}%): " + " · ".join(parts))
    if near_lines == 0:
        ngrade = sum(1 for t in FOURTEEN if nt[t]["status"] == "GRADED")
        A(f"- None — all {ngrade} gradable exhibit names were admitted at some point in the "
          f"window under EVERY variant, including LIVE. For them the gate's failure was "
          f"LATENESS, not an outright veto (read the run-up column and the first-admission "
          f"dates above); for the other {len(FOURTEEN) - ngrade} it was the missing-data / "
          f"young-name wall in the `could never see` list.")
    A("")
    A("## 4. Reading rules")
    A("")
    A("- Nothing here promotes anything. Under house epistemics the gauntlet is a PROMOTION "
      "gate, not a build gate; these are display-tier measurements and a null blocks nothing.")
    A("- Denominators are TIME-truncated, never outcome-truncated. Admission days without an "
      "H=10 forward are counted in `unscored` and excluded from BOTH the numerator and the "
      "denominator of every rate, identically across variants.")
    A("- Pooled cells double-count a name that sits in a state for weeks; read the per-name-first "
      "column beside them, and treat any row marked THIN as directional only.")
    A("- The 14 names are an exhibit. They enter no cohort statistic.")
    A("")
    A(f"Raw: `research/prophet_us_audit/{Path(OUT_JSON).name}`")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()
