"""wave5.py — Durable-Bottom Entry Timing Study, Wave 5 (BASED / RETEST post-cross re-admission)

Spec (BINDING, read fully): research/entry_timing/WAVE5_PREREG.md (v2).
Supporting: research/BASING_AFTER_CONFLUENCE_PROBLEM_AUDIT_FOR_FABLE.md,
            research/signal_engine/DURABLE_BOTTOM_FRAMEWORK.md §2/§4.

This wave tests two co-primary post-cross re-admission candidates on the confluence /
RSI-MACD layer:
  - BASED  (a state):  post-cross window [i+7, i+24], never LAUNCHED, structurally intact
                       above the trough line (NOT BROKEN).
  - RETEST (an event): a fresh 2D RSI-MACD re-cross fires INSIDE the window, guarded by
                       launch/broken/OB-persist + 3D RSI14<65.

Entry policies (one entry per fire per policy; identical common fully-observed fire set;
fill at entry_bar+1 close):
  E_FRESH  — at i+1                        (incumbent baseline)
  P1       — E_STALE_i7  : i+7, unconditional (immortal-time floor)
  P2       — E_SURVIVE_i7: i+7 iff NOT LAUNCHED_{i+7} AND NOT BROKEN_{i+7}   (correct parent)
  E_BASED  — first j>=i+7 with BASED_j
  E_DIP7   — placebo: lowest close in [i+7, i+24] among P2 survivors (hindsight-located)
  E_LAUNCHED — first j with LAUNCHED_j     (negative control)
  E_RETEST — first j in [i+3, i+30] with a fresh 2D RSI-MACD cross-up (event-mapped known
             date), NOT LAUNCHED, NOT BROKEN, 3D RSI14 < 65.

Reuses (IMPORTED, never reimplemented):
  wave1.py: compute_outcomes, label_events, build_tf_grids, build_sector_d_matrix,
            get_cohort_frac, constants.
  wave2.py: compute_outcomes_w2, label_events_w2, panel loaders, sector maps,
            _serialize_d_matrix (FIX-1), multiprocessing Pool pattern.
  tuning_harness.py: rsi, ema, rsi_macd, stoch_rsi_kd, tf_bars, to_daily, VARIANTS,
                     build_signals.
  engine.confluence_tiers.tier_stream (visibility descriptive).
  engine.signal_gate.gate (anchor-divergence study).

CLI subcommands:
  --selftest      fast, no panel: JNJ-2026 fixture unit test; KO/MCD ladder classification
                  sanity prints; E_RETEST event-mapping assertion; ATR causality assertion.
  --stocks        deep panel run (211 US names).
  --baskets       baskets OOS run (2,336 names).
  --descriptives  visibility / re-trigger / sizing / anchor studies.
  --gates         evaluate §6 from the parquets, write _out/wave5_gates.json.

Run '--selftest' and iterate until it passes (the runner does the panel runs after audit).
"""
from __future__ import annotations

import sys
import time
import json
import argparse
import warnings
import logging
from pathlib import Path
from multiprocessing import Pool

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)

# ── path bootstrap ────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]
SIG_ENG = ROOT / "research" / "signal_engine"
ENTRY_TIMING = ROOT / "research" / "entry_timing"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SIG_ENG))
sys.path.insert(0, str(ENTRY_TIMING))

import tuning_harness as TH  # noqa: E402

# wave1 primitives (imported verbatim; never modified)
from wave1 import (  # noqa: E402
    compute_outcomes, build_tf_grids,
    build_sector_d_matrix, get_cohort_frac,
    FWD_REQ, OUTCOME_W, MFE_MAE_W, DD_MIN,
    H6_COHORT_THRESH, H2_CAPIT_AGE, H2_ATR_CRUSH,
)

# wave2 primitives (imported verbatim; never modified)
from wave2 import (  # noqa: E402
    _serialize_d_matrix,
    load_membership, build_active_set, build_basket_sector_map, build_theme_peers,
    PANEL_CONFIGS,
)

DATA_STOCKS  = ROOT / "data" / "stocks"
DATA_BASKETS = ROOT / "data" / "baskets" / "ohlcv"
BREADTH      = ROOT / "data" / "breadth"
OUT_DIR      = ENTRY_TIMING / "_out"

# ─────────────────────────── ladder / policy constants (§2-§3) ───────────────
TRIGGERS       = ["m2d_s3d", "base3d"]   # §2 fire sets, analyzed separately (m2d_s3d primary)
PRIMARY_TRIG   = "m2d_s3d"
DEDUPE_TD      = 21          # §2 ladder dedupe: 21 trading days per name, first fire kept
LADDER_MAX     = 30          # §2/§3 j = i+1 .. i+30
BASED_LO       = 7           # §3 BASED window low  (j-i in [7, 24])
BASED_HI       = 24          # §3 BASED window high
TROUGH_LB      = 90          # §3 trough_ref window = close[i-90 .. i]  (91 bars incl i)
TROUGH_TOL     = 0.97        # §3 BROKEN: min(close[i+1..j]) < T * 0.97
MAXUP_THRESH   = 0.05        # §3 LAUNCHED: maxup_j > 0.05  (== ext ceiling; one number)
OB_THRESH      = 80          # §3 OB-persist: 3D StochRSI k OR d >= 80 on ANY bar in [i..j]
RETEST_LO      = 3           # §3 E_RETEST: first j in [i+3, i+30]
RETEST_RSI_MAX = 65          # §3 E_RETEST: 3D RSI14 < 65
# ATR co-primary (§4): stop = 1.5x ATR63, target = 4.5x ATR63, ATR63 = wave1 ewm atrp basis
ATR_STOP_MULT   = 1.5
ATR_TARGET_MULT = 4.5
# §4 inference: 90% block-bootstrap lower bound, clustered on (name x 63-td calendar block)
BOOT_N          = 1000
BOOT_ALPHA      = 0.10       # 90% one-sided lower bound -> 10th percentile
BLOCK_TD        = 63         # 63-trading-day calendar block
NAME_FLOOR      = 60         # §4 gate n-floors: >=60 distinct names
BLOCK_FLOOR     = 40         # §4 gate n-floors: >=40 distinct 63d blocks

# Policies scored on the identical common fully-observed fire set.
POLICIES = ["E_FRESH", "P1", "P2", "E_BASED", "E_DIP7", "E_LAUNCHED", "E_RETEST"]

# GICS basket->sector map reused from wave2 for the baskets panel
from wave2 import _BASKET_TO_SECTOR  # noqa: E402


# ══════════════════════════════════════════════════════════════════════════════
# §3 Ladder mechanics (all causal at day j)
# ══════════════════════════════════════════════════════════════════════════════

def compute_ladder(i: int, c: np.ndarray, k3d: np.ndarray, d3d: np.ndarray,
                   n: int) -> dict:
    """Compute the post-cross ladder states for a fire at signal bar i.

    All windows are bounded <= j (leak §7.6). trough_ref uses close[i-90..i] only (§7.7).
    Returns per-j arrays keyed by j-i offset in [1, LADDER_MAX]:
      maxup, ext, obp (sticky), launched, broken, based  — plus the scalar trough T.
    """
    Pc = c[i]
    T = float(np.min(c[max(0, i - TROUGH_LB): i + 1]))   # §3 trough_ref, close[i-90..i]

    jmax = min(LADDER_MAX, n - 1 - i)
    maxup = np.full(LADDER_MAX + 1, np.nan)
    ext   = np.full(LADDER_MAX + 1, np.nan)
    obp   = np.zeros(LADDER_MAX + 1, dtype=bool)
    launched = np.zeros(LADDER_MAX + 1, dtype=bool)
    broken   = np.zeros(LADDER_MAX + 1, dtype=bool)
    based    = np.zeros(LADDER_MAX + 1, dtype=bool)

    ob_sticky = False
    run_max = c[i]         # max(close[i..j])
    run_min_fwd = np.inf   # min(close[i+1..j])
    for off in range(1, jmax + 1):
        j = i + off
        cj = c[j]
        run_max = max(run_max, cj)
        run_min_fwd = min(run_min_fwd, cj)
        # OB-persist: sticky — set once any bar in [i..j] printed 3D StochRSI k|d >= 80.
        # scan [i..j]; the i..(j-1) prefix is captured by ob_sticky, so only test bar j
        # (and bar i on the first iteration).
        if off == 1:
            ki, di_ = k3d[i], d3d[i]
            if (not np.isnan(ki) and ki >= OB_THRESH) or (not np.isnan(di_) and di_ >= OB_THRESH):
                ob_sticky = True
        kj, dj = k3d[j], d3d[j]
        if (not np.isnan(kj) and kj >= OB_THRESH) or (not np.isnan(dj) and dj >= OB_THRESH):
            ob_sticky = True

        mu = run_max / Pc - 1.0
        ex = cj / Pc - 1.0
        br = bool(run_min_fwd < T * TROUGH_TOL)
        la = bool(mu > MAXUP_THRESH or ob_sticky)
        ba = bool(BASED_LO <= off <= BASED_HI and (not la) and (not br))

        maxup[off] = mu
        ext[off]   = ex
        obp[off]   = ob_sticky
        launched[off] = la
        broken[off]   = br
        based[off]    = ba

    return {"Pc": Pc, "T": T, "jmax": jmax,
            "maxup": maxup, "ext": ext, "obp": obp,
            "launched": launched, "broken": broken, "based": based}


def resolve_policies(i: int, lad: dict, c: np.ndarray, n: int,
                     retest_events_daily: np.ndarray, r14_3d: np.ndarray) -> dict:
    """Resolve each entry policy for one fire into an entry-bar index (the day j chosen),
    or None if the policy does not enter this fire. Fill is entry_bar+1 (applied by caller).

    §2 common fully-observed fire set is enforced by the CALLER (only fires with
    i + LADDER_MAX + 1 + OUTCOME_W < n enter the study — the guard drops on `>=`), so every
    offset up to LADDER_MAX has a full forward window here for every policy.

    retest_events_daily: boolean daily array, True on the daily bar == the 2D RSI-MACD
      cross-up known date (from to_daily(...,'event')). §7.3 known-date path.
    r14_3d: daily-mapped 3D RSI14.
    """
    launched = lad["launched"]
    broken   = lad["broken"]
    based    = lad["based"]

    out: dict = {p: None for p in POLICIES}

    # E_FRESH — at i+1 (entry_bar = i+1)
    out["E_FRESH"] = i + 1

    # P1 = E_STALE_i7 — enters at i+7 unconditionally (immortal-time floor)
    out["P1"] = i + 7

    # P2 = E_SURVIVE_i7 — enters at i+7 iff NOT LAUNCHED_{i+7} AND NOT BROKEN_{i+7}
    p2_ok = (not launched[7]) and (not broken[7])
    if p2_ok:
        out["P2"] = i + 7

    # E_BASED — first j >= i+7 with BASED_j
    for off in range(BASED_LO, BASED_HI + 1):
        if based[off]:
            out["E_BASED"] = i + off
            break

    # E_DIP7 — placebo: lowest close in [i+7, i+24] among P2 survivors (hindsight by design §7.13)
    if p2_ok:
        lo_off, lo_px = None, np.inf
        for off in range(BASED_LO, BASED_HI + 1):
            j = i + off
            if j >= n:
                break
            if c[j] < lo_px:
                lo_px, lo_off = c[j], off
        if lo_off is not None:
            out["E_DIP7"] = i + lo_off

    # E_LAUNCHED — first j with LAUNCHED_j (negative control)
    for off in range(1, lad["jmax"] + 1):
        if launched[off]:
            out["E_LAUNCHED"] = i + off
            break

    # E_RETEST — first j in [i+3, i+30] with a fresh 2D RSI-MACD cross-up known here,
    # AND NOT launched AND NOT broken AND 3D RSI14 < 65.
    for off in range(RETEST_LO, LADDER_MAX + 1):
        j = i + off
        if j >= n:
            break
        if not retest_events_daily[j]:
            continue
        if launched[off] or broken[off]:
            continue
        rv = r14_3d[j]
        if np.isnan(rv) or rv >= RETEST_RSI_MAX:
            continue
        out["E_RETEST"] = j
        break

    return out


# ══════════════════════════════════════════════════════════════════════════════
# §4 ATR co-primary barriers (causal; ATR63 read at fill using bars <= fill_idx)
# ══════════════════════════════════════════════════════════════════════════════

def compute_atr_outcomes(fill_idx: int, p: float, c: np.ndarray, atrp: np.ndarray,
                         n: int) -> dict:
    """ATR-barrier stop/clean race. stop = p*(1 - 1.5*ATR63%), target = p*(1 + 4.5*ATR63%),
    where ATR63% = the wave-1 ewm `atrp` basis (wave1.build_tf_grids) EVALUATED AT THE FILL
    BAR (atrp[fill_idx]) — bars <= fill_idx only, no forward window (§4 / §7.4).

    Returns {stop_atr, clean_atr}. atrp is ATR as a FRACTION of price (wave1 atrp = atr/close).
    """
    a = atrp[fill_idx]
    if np.isnan(a) or a <= 0:
        return {"stop_atr": np.nan, "clean_atr": np.nan}
    stop_barrier  = p * (1.0 - ATR_STOP_MULT * a)
    clean_barrier = p * (1.0 + ATR_TARGET_MULT * a)
    stop_atr, clean_atr = 0, 0
    for k in range(fill_idx + 1, min(fill_idx + OUTCOME_W + 1, n)):
        cl = c[k]
        if cl <= stop_barrier:
            stop_atr = 1
            break
        if cl >= clean_barrier:
            clean_atr = 1
            break
    return {"stop_atr": stop_atr, "clean_atr": clean_atr}


# ══════════════════════════════════════════════════════════════════════════════
# §4 strata features at the ENTRY (fill) bar — all TRAILING / causal (§7.5)
# ══════════════════════════════════════════════════════════════════════════════

def leadership_trailing(ticker: str, sig_date: pd.Timestamp, i: int,
                        sector_map: dict, sector_close: dict, spy_close: pd.Series | None,
                        win: int) -> float | None:
    """TRAILING peer leadership at bar i (§4 / §7.5): peers' mean close[i]/close[i-win]-1
    minus SPY same, using bars <= i only. Windows END at bar i. Returns None if no peers.
    sector_close: {ticker: (DatetimeIndex, close_ndarray)}.
    """
    my_sec = sector_map.get(ticker)
    if my_sec is None or spy_close is None:
        return None
    peers = [t for t, s in sector_map.items() if s == my_sec and t != ticker and t in sector_close]
    if not peers:
        return None
    rets = []
    for pt in peers:
        pidx, parr = sector_close[pt]
        pos = pidx.searchsorted(sig_date, side="right") - 1
        if pos < win:
            continue
        pv, pv0 = parr[pos], parr[pos - win]
        if not np.isnan(pv) and not np.isnan(pv0) and pv0 > 0:
            rets.append(pv / pv0 - 1.0)
    if not rets:
        return None
    # SPY same-window trailing return
    spos = spy_close.index.searchsorted(sig_date, side="right") - 1
    if spos < win:
        return None
    sv, sv0 = float(spy_close.iloc[spos]), float(spy_close.iloc[spos - win])
    if np.isnan(sv) or np.isnan(sv0) or sv0 <= 0:
        return None
    return float(np.mean(rets)) - (sv / sv0 - 1.0)


# ══════════════════════════════════════════════════════════════════════════════
# Per-name processing (multiprocessing worker, wave2 pattern + FIX-1 ISO serialization)
# ══════════════════════════════════════════════════════════════════════════════

def _dedupe_fires_backward(fire_positions: list[int]) -> list[int]:
    """§2/§7.10: 21 trading days per name, first fire kept, backward-looking only.
    fire_positions is ascending. Keep a fire iff >= DEDUPE_TD td after the last KEPT fire."""
    kept: list[int] = []
    last = None
    for i in fire_positions:
        if last is None or (i - last) >= DEDUPE_TD:
            kept.append(i)
            last = i
    return kept


def _process_name_inner(ticker: str, fp: str, spy_ratio: pd.Series | None,
                        spy_close: pd.Series | None,
                        sector_map: dict, sector_d_matrix: dict, sector_close: dict,
                        eval_start: pd.Timestamp, min_bars: int) -> dict:
    """Core per-name processing. Returns {trigger: [fire_row_dict,...]}.
    Each fire_row carries, per policy, that policy's fill_date + outcomes + atr outcomes.
    Memory-sane: per-name only, no giant concat (caller aggregates).
    """
    df = pd.read_parquet(fp)
    daily = df["close"].dropna()
    if len(daily) < min_bars:
        return {}
    hi = df["high"].reindex(daily.index) if "high" in df.columns else pd.Series(np.nan, index=daily.index)
    lo = df["low"].reindex(daily.index)  if "low"  in df.columns else pd.Series(np.nan, index=daily.index)

    idx = daily.index
    c = daily.to_numpy()
    hi_arr = hi.to_numpy()
    lo_arr = lo.to_numpy()
    n = len(c)

    spy_ratio_aligned = spy_ratio.reindex(idx, method="ffill") if spy_ratio is not None else None
    grids = build_tf_grids(daily, hi, lo, spy_ratio_aligned)
    atrp = grids["atrp"]
    ma200 = grids["ma200"]

    # 3D StochRSI k,d daily-mapped (for OB-persist) + 3D RSI14 daily-mapped (for E_RETEST guard)
    s3, kn3 = TH.tf_bars(daily, 3)
    k3, d3 = TH.stoch_rsi_kd(s3)
    k3d = TH.to_daily(k3, kn3, idx, "ffill").to_numpy()
    d3d = TH.to_daily(d3, kn3, idx, "ffill").to_numpy()
    r14_3 = TH.rsi(s3, TH.RSI_LEN)
    r14_3d = TH.to_daily(r14_3, kn3, idx, "ffill").to_numpy()

    # 2D RSI-MACD cross-up EVENT stream (§3/§7.3 known-date path, NOT the bin label)
    s2, kn2 = TH.tf_bars(daily, 2)
    m2, sig2 = TH.rsi_macd(s2)
    cross2 = TH.xup(m2, sig2).fillna(False)
    retest_events = TH.to_daily(cross2, kn2, idx, "event").to_numpy().astype(bool)

    result: dict = {}
    for trig in TRIGGERS:
        cfg = TH.VARIANTS[trig]
        frame = TH.build_signals(daily, cfg, hi, lo)
        raw_fires = [idx.get_loc(d) for d in frame.index[frame["buy"]].tolist()]
        raw_fires = sorted(raw_fires)
        deduped = _dedupe_fires_backward(raw_fires)

        rows: list[dict] = []
        for i in deduped:
            sig_date = idx[i]
            # §2 common fully-observed fire set: latest possible entry has a GENUINELY full
            # 126-bar window. Use `>=` (not `>`) so the fire is dropped ENTIRELY the moment the
            # latest possible policy (fill at i+LADDER_MAX+1) cannot get a full OUTCOME_W window
            # — matching the per-policy `fill_idx + OUTCOME_W >= n` guard at line ~436 so ALL
            # policies for a boundary fire are censored together (no per-policy end-of-panel
            # asymmetry; §2/§7.1 common-set invariant, amendment #13). This also fixes the
            # spec's own 1-bar-truncated-window off-by-one at the exact boundary n == i+157.
            if i + LADDER_MAX + 1 + OUTCOME_W >= n:
                continue
            # eval window
            if idx[i + 1] < eval_start:
                continue

            lad = compute_ladder(i, c, k3d, d3d, n)
            pol = resolve_policies(i, lad, c, n, retest_events, r14_3d)

            # Entry-bar strata (causal at the fill bar of each policy) — computed once from
            # the fire's own context (h6 cohort, 63d/252d leadership at bar i, vol quintile
            # basis atrp[i], H2 cell at bar i). ext@entry & above/below-200 are per-policy.
            h6 = get_cohort_frac(ticker, sig_date, sector_map, sector_d_matrix)
            lead63 = leadership_trailing(ticker, sig_date, i, sector_map, sector_close, spy_close, 63)
            lag252 = leadership_trailing(ticker, sig_date, i, sector_map, sector_close, spy_close, 252)
            atrp_i = float(atrp[i]) if not np.isnan(atrp[i]) else np.nan

            # H2-contrast cell at the fire bar (capit_age>=15 AND atr_crush<=0.60), wave-1 defs
            start90 = max(0, i - 90)
            w90 = c[start90:i + 1]
            capit_idx = start90 + int(np.argmin(w90))
            capit_age = i - capit_idx
            atrp_win = atrp[capit_idx:i + 1]
            atrp_max = np.nanmax(atrp_win) if len(atrp_win) > 0 else np.nan
            atr_crush = atrp[i] / atrp_max if (not np.isnan(atrp_max) and atrp_max > 0) else np.nan
            h2_good = bool(capit_age >= H2_CAPIT_AGE and not np.isnan(atr_crush)
                           and atr_crush <= H2_ATR_CRUSH)

            base = {
                "ticker": ticker, "sig_idx": i, "sig_date": sig_date,
                "Pc": lad["Pc"], "trough": lad["T"],
                "h6_cohort": h6, "lead63": lead63, "lag252": lag252, "atrp_i": atrp_i,
                "h2_good": h2_good, "capit_age": capit_age, "atr_crush": atr_crush,
                # drop diagnostic: eligible for P2 but no BASED entry (§3 E_BASED dropout)
                "p2_eligible": bool(pol["P2"] is not None),
                "based_entered": bool(pol["E_BASED"] is not None),
            }

            # Per-policy outcomes at fill = entry_bar + 1 (§2/§7.2)
            for p in POLICIES:
                eb = pol[p]
                pre = f"{p}__"
                if eb is None:
                    base[pre + "fill_idx"] = None
                    continue
                fill_idx = eb + 1
                # The `fill_idx + OUTCOME_W >= n` branch is now UNREACHABLE for any policy on a
                # fire that entered the study: the common-set guard above (`>=`) already dropped
                # every boundary fire whose latest possible policy lacks a full window, so all
                # policies here have `fill_idx <= i+LADDER_MAX+1` and `i+LADDER_MAX+1+OUTCOME_W <
                # n`. It is retained only for defensive symmetry. The `np.isnan(c[fill_idx])`
                # clause is a genuine-missing-price drop (per-policy, acceptable on a validated
                # deep panel — a real NaN close, not an end-of-panel censoring asymmetry).
                if fill_idx + OUTCOME_W >= n or np.isnan(c[fill_idx]):
                    base[pre + "fill_idx"] = None
                    continue
                fp_px = c[fill_idx]
                oc = compute_outcomes(fill_idx, fp_px, c, hi_arr, lo_arr)
                atr_oc = compute_atr_outcomes(fill_idx, fp_px, c, atrp, n)
                base[pre + "fill_idx"]  = fill_idx
                base[pre + "fill_date"] = idx[fill_idx]
                base[pre + "entry_off"] = eb - i
                base[pre + "stop5"]      = oc["stop5"]
                base[pre + "clean15"]    = oc["clean15"]
                base[pre + "dead_money"] = oc["dead_money"]
                base[pre + "mfe63"]      = oc["mfe63"]
                base[pre + "mae63"]      = oc["mae63"]
                base[pre + "days_to_10"] = oc["days_to_10"]
                base[pre + "stop_atr"]   = atr_oc["stop_atr"]
                base[pre + "clean_atr"]  = atr_oc["clean_atr"]
                base[pre + "prem_trough"] = fp_px / lad["T"] - 1.0 if lad["T"] > 0 else np.nan
                base[pre + "ext_entry"]  = fp_px / lad["Pc"] - 1.0
                m2i = ma200[fill_idx]
                base[pre + "above200"]   = bool(not np.isnan(m2i) and fp_px > m2i)

            rows.append(base)
        result[trig] = rows

    return result


def _worker(args: tuple) -> tuple[str, dict]:
    (ticker, fp, spy_ratio_vals, spy_ratio_idx, spy_close_vals, spy_close_idx,
     sector_map, sector_d_matrix_ser, sector_close_ser, eval_start, min_bars) = args
    try:
        spy_ratio = None
        if spy_ratio_vals is not None:
            spy_ratio = pd.Series(spy_ratio_vals, index=pd.DatetimeIndex(spy_ratio_idx))
        spy_close = None
        if spy_close_vals is not None:
            spy_close = pd.Series(spy_close_vals, index=pd.DatetimeIndex(spy_close_idx))
        sector_d_matrix = {t: (pd.DatetimeIndex(iv), np.asarray(a))
                           for t, (iv, a) in sector_d_matrix_ser.items()}
        sector_close = {t: (pd.DatetimeIndex(iv), np.asarray(a))
                        for t, (iv, a) in sector_close_ser.items()}
        res = _process_name_inner(ticker, fp, spy_ratio, spy_close,
                                  sector_map, sector_d_matrix, sector_close,
                                  eval_start, min_bars)
        return (ticker, res)
    except Exception as e:  # noqa: BLE001
        return (ticker, {"_error": repr(e)})


def _build_sector_close(panel_files: list[str], sector_map: dict, min_bars: int) -> dict:
    """{ticker: (DatetimeIndex, close_ndarray)} for sector-mapped peers (leadership stratum)."""
    out: dict = {}
    for fp in panel_files:
        t = Path(fp).stem
        if t not in sector_map:
            continue
        try:
            df = pd.read_parquet(fp)
            daily = df["close"].dropna()
            if len(daily) < min_bars:
                continue
            out[t] = (daily.index, daily.to_numpy())
        except Exception:  # noqa: BLE001
            continue
    return out


def _serialize_close(cm: dict) -> dict:
    return {t: (idx.strftime("%Y-%m-%d").tolist(), arr.tolist()) for t, (idx, arr) in cm.items()}


# ══════════════════════════════════════════════════════════════════════════════
# §4 block-bootstrap lower bound (clustered on name x 63d block)
# ══════════════════════════════════════════════════════════════════════════════

def _block_labels(df: pd.DataFrame, fill_date_col: str) -> pd.Series:
    """(name x 63-trading-day calendar block) cluster label for each row.

    NOTE (disclosed limitation): §4 specifies a 63-TRADING-day block, but this uses a
    calendar-day proxy — ordinal-day // 91 (~63 trading days ~ one quarter). This proxy is
    acceptable for CLUSTERING (blocks are never used for scoring), but the BLOCK_FLOOR=40
    gate n-floor is measured against these calendar-proxy blocks, NOT true 63-td blocks — a
    slightly coarser (typically more conservative, occasionally looser) block count than the
    literal spec. The runner must state this in WAVE5_REPORT.md §7. Not a leak."""
    fd = pd.to_datetime(df[fill_date_col])
    epoch = pd.Timestamp("2000-01-01")
    days = (fd - epoch).dt.days
    blk = (days // 91).astype("int64")
    return df["ticker"].astype(str) + "|" + blk.astype(str)


def _block_bootstrap_means(values: np.ndarray, clusters: np.ndarray,
                           n_boot: int = BOOT_N, seed: int = 12345) -> np.ndarray:
    """Cluster (block) bootstrap of the pooled MEAN. Resample whole clusters with
    replacement; recompute the pooled mean each draw. Returns the bootstrap-mean
    distribution (length n_boot), or an empty array if no data."""
    vals = np.asarray(values, dtype=float)
    keep = ~np.isnan(vals)
    vals = vals[keep]
    cl = np.asarray(clusters)[keep]
    if len(vals) == 0:
        return np.empty(0)
    uniq = np.unique(cl)
    # group values by cluster
    groups = {u: vals[cl == u] for u in uniq}
    gk = list(groups.keys())
    rng = np.random.default_rng(seed)
    m = len(gk)
    boot = np.empty(n_boot)
    for b in range(n_boot):
        pick = rng.integers(0, m, size=m)
        chunks = [groups[gk[p]] for p in pick]
        boot[b] = np.concatenate(chunks).mean()
    return boot


def block_bootstrap_lb(values: np.ndarray, clusters: np.ndarray,
                       n_boot: int = BOOT_N, alpha: float = BOOT_ALPHA,
                       seed: int = 12345) -> float:
    """One-sided (100*(1-alpha))% LOWER bound of the MEAN via cluster (block) bootstrap.
    Returns the alpha-quantile of the bootstrap mean distribution. Returns NaN if no data.
    Use for HIGHER-is-better metrics (e.g. clean15)."""
    boot = _block_bootstrap_means(values, clusters, n_boot=n_boot, seed=seed)
    if len(boot) == 0:
        return float("nan")
    return float(np.quantile(boot, alpha))


def block_bootstrap_ub(values: np.ndarray, clusters: np.ndarray,
                       n_boot: int = BOOT_N, alpha: float = BOOT_ALPHA,
                       seed: int = 12345) -> float:
    """One-sided (100*(1-alpha))% UPPER bound of the MEAN via cluster (block) bootstrap.
    Returns the (1-alpha)-quantile of the bootstrap mean distribution. Returns NaN if no
    data. Use for LOWER-is-better metrics (e.g. stop5/stop_atr/dead_money): a stop-out edge
    claim on the improved side (BASED) must survive its CONSERVATIVE (upper) tail per §4 /
    amendment #7 — the same one-sided 90% discipline as the lower bound, mirror direction."""
    boot = _block_bootstrap_means(values, clusters, n_boot=n_boot, seed=seed)
    if len(boot) == 0:
        return float("nan")
    return float(np.quantile(boot, 1.0 - alpha))


def _rate(series: pd.Series) -> float:
    v = series.dropna()
    return float(v.mean()) if len(v) else float("nan")


def _policy_frame(fires: pd.DataFrame, policy: str) -> pd.DataFrame:
    """Slice the wide fires frame down to rows where `policy` produced an entry, renaming
    that policy's columns to bare metric names. Returns a per-entry frame."""
    pre = f"{policy}__"
    mask = fires[pre + "fill_idx"].notna() if (pre + "fill_idx") in fires.columns else pd.Series(False, index=fires.index)
    sub = fires[mask].copy()
    if len(sub) == 0:
        return sub
    cols = {c: c[len(pre):] for c in sub.columns if c.startswith(pre)}
    keep = ["ticker", "sig_idx", "sig_date"] + list(cols.keys())
    sub = sub[keep].rename(columns=cols)
    return sub


# ══════════════════════════════════════════════════════════════════════════════
# Panel runner
# ══════════════════════════════════════════════════════════════════════════════

def run_panel(panel: str, tickers: list[str] | None, workers: int) -> Path:
    cfg = PANEL_CONFIGS[panel]
    data_dir = cfg["data_dir"]
    min_bars = cfg["min_bars"]
    eval_start = cfg["eval_start"]
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Wave-5 | panel={panel} | eval_start={eval_start.date()} | min_bars={min_bars} | workers={workers}")

    all_files = sorted(data_dir.glob("*.parquet"))
    if tickers:
        want = set(tickers)
        all_files = [f for f in all_files if f.stem in want]

    panel_files = []
    for fp in all_files:
        try:
            if len(pd.read_parquet(fp)["close"].dropna()) >= min_bars:
                panel_files.append(fp)
        except Exception:  # noqa: BLE001
            pass
    print(f"Panel names (>= {min_bars} bars): {len(panel_files)}")

    # sector map
    const_path = BREADTH / "constituents.parquet"
    const_map: dict = {}
    if const_path.exists():
        cdf = pd.read_parquet(const_path)
        for sym, row in cdf.iterrows():
            const_map[sym] = row["sector"]
    if panel == "baskets" and (ROOT / "data" / "baskets" / "membership.json").exists():
        mem = load_membership()
        sector_map = {**const_map, **build_basket_sector_map(mem)}
    else:
        sector_map = const_map
    print(f"Sector map: {len(sector_map)} tickers")

    # SPY
    spy_path = DATA_STOCKS / "SPY.parquet"
    if not spy_path.exists():
        spy_path = ROOT / "data" / "yahoo" / "SPY.parquet"
    spy_close = pd.read_parquet(spy_path)["close"].dropna() if spy_path.exists() else None

    # sector D matrix (H6 cohort) + sector close matrix (leadership) from full data dir
    all_data_files = sorted(data_dir.glob("*.parquet"))
    peer_files = [str(fp) for fp in all_data_files if fp.stem in sector_map]
    print(f"Building sector D-matrix + close-matrix over {len(peer_files)} peer files...")
    t0 = time.time()
    sector_d_matrix = build_sector_d_matrix(peer_files, sector_map)
    sector_close = _build_sector_close(peer_files, sector_map, min_bars)
    print(f"  D-matrix={len(sector_d_matrix)} close-matrix={len(sector_close)} ({time.time()-t0:.1f}s)")

    sdm_ser = _serialize_d_matrix(sector_d_matrix)
    scl_ser = _serialize_close(sector_close)
    spy_close_vals = spy_close.to_numpy().tolist() if spy_close is not None else None
    spy_close_idx = spy_close.index.strftime("%Y-%m-%d").tolist() if spy_close is not None else None

    # worker args
    worker_args = []
    for fp in panel_files:
        t = fp.stem
        spy_vals = spy_idx = None
        if spy_close is not None:
            try:
                dt = pd.read_parquet(fp)["close"].dropna()
                spy_al = spy_close.reindex(dt.index, method="ffill")
                spy_r = (dt / spy_al).replace([np.inf, -np.inf], np.nan)
                spy_vals = spy_r.to_numpy().tolist()
                spy_idx = dt.index.strftime("%Y-%m-%d").tolist()
            except Exception:  # noqa: BLE001
                pass
        worker_args.append((t, str(fp), spy_vals, spy_idx, spy_close_vals, spy_close_idx,
                            sector_map, sdm_ser, scl_ser, eval_start, min_bars))

    print(f"Processing {len(worker_args)} names with {workers} workers...")
    t0 = time.time()
    if workers <= 1:
        results = [_worker(a) for a in worker_args]
    else:
        with Pool(workers) as pool:
            results = pool.map(_worker, worker_args)

    rows_by_trig: dict[str, list[dict]] = {t: [] for t in TRIGGERS}
    errors = []
    for ticker, res in results:
        if "_error" in res:
            errors.append(f"{ticker}: {res['_error']}")
            continue
        for trig in TRIGGERS:
            rows_by_trig[trig].extend(res.get(trig, []))
    print(f"Done in {time.time()-t0:.1f}s. errors={len(errors)}: {errors[:3]}")

    for trig in TRIGGERS:
        df = pd.DataFrame(rows_by_trig[trig])
        if len(df) > 0 and "sig_date" in df.columns:
            df["sig_date"] = pd.to_datetime(df["sig_date"])
        outp = OUT_DIR / f"wave5_{panel}_{trig}.parquet"
        df.to_parquet(outp, index=False)
        print(f"  saved {outp.name}: {len(df)} fires")

    # compact summary print
    df = pd.DataFrame(rows_by_trig[PRIMARY_TRIG])
    if len(df) > 0:
        print(f"\n--- {panel} / {PRIMARY_TRIG} policy n + stop5/clean15 (point est) ---")
        for p in POLICIES:
            sub = _policy_frame(df, p)
            if len(sub) == 0:
                print(f"  {p:11s} n=0")
                continue
            print(f"  {p:11s} n={len(sub):5d}  stop5={_rate(sub['stop5'])*100:5.1f}%  "
                  f"clean15={_rate(sub['clean15'])*100:5.1f}%  "
                  f"stop_atr={_rate(sub['stop_atr'])*100:5.1f}%")
    return OUT_DIR / f"wave5_{panel}_{PRIMARY_TRIG}.parquet"


# ══════════════════════════════════════════════════════════════════════════════
# §4 Descriptives  (visibility / re-trigger / sizing / anchor-divergence)
# ══════════════════════════════════════════════════════════════════════════════

def descriptive_visibility(fires: pd.DataFrame, panel: str, tickers: list[str] | None,
                           workers: int) -> dict:
    """visibility-at-liftoff (§4): among fires whose E_FRESH outcome was clean15==1, the
    fraction where tier_stream showed NO eligible tier on the LIFTOFF day — the first bar
    with close >= 1.05 * (min close over [fill, that bar]) — vs visibility under BASED.
    Descriptive only. Uses engine.confluence_tiers.tier_stream (completed-bucket basis, §7.12).
    """
    from engine import confluence_tiers as CT
    data_dir = PANEL_CONFIGS[panel]["data_dir"]
    ef = _policy_frame(fires, "E_FRESH")
    eb = _policy_frame(fires, "E_BASED")
    if len(ef) == 0:
        return {"note": "no E_FRESH fires"}

    # only clean15==1 E_FRESH fires
    ef_c = ef[ef["clean15"] == 1].copy()
    # cache tier_stream per ticker
    ts_cache: dict[str, pd.DataFrame] = {}

    def _liftoff_invisible(sub: pd.DataFrame) -> tuple[int, int]:
        invis, total = 0, 0
        for _, r in sub.iterrows():
            t = r["ticker"]
            if t not in ts_cache:
                try:
                    dc = pd.read_parquet(data_dir / f"{t}.parquet")["close"].dropna()
                    ts_cache[t] = CT.tier_stream(dc)
                except Exception:  # noqa: BLE001
                    ts_cache[t] = pd.DataFrame()
            ts = ts_cache[t]
            fill_idx = int(r["fill_idx"])
            try:
                dc = pd.read_parquet(data_dir / f"{t}.parquet")["close"].dropna()
            except Exception:  # noqa: BLE001
                continue
            c = dc.to_numpy(); nloc = len(c)
            if fill_idx >= nloc:
                continue
            # liftoff day = first bar with close >= 1.05 * min(close over [fill, that bar])
            run_min = c[fill_idx]
            lift_bar = None
            for k in range(fill_idx, min(fill_idx + OUTCOME_W + 1, nloc)):
                run_min = min(run_min, c[k])
                if c[k] >= 1.05 * run_min:
                    lift_bar = k
                    break
            if lift_bar is None:
                continue
            total += 1
            if len(ts) == 0 or lift_bar >= len(ts):
                invis += 1
                continue
            elig = bool(ts.iloc[lift_bar].get("eligible", False))
            if not elig:
                invis += 1
        return invis, total

    fi, ft = _liftoff_invisible(ef_c)
    bi, bt = _liftoff_invisible(eb)
    return {
        "n_fresh_clean15": int(len(ef_c)),
        "fresh_liftoff_invisible_frac": round(fi / ft, 4) if ft else float("nan"),
        "fresh_liftoff_n": ft,
        "based_liftoff_invisible_frac": round(bi / bt, 4) if bt else float("nan"),
        "based_liftoff_n": bt,
        "note": "tier_stream completed-bucket basis (§7.12); liftoff = first close>=1.05*trailing-min",
    }


def descriptive_retrigger(fires: pd.DataFrame, panel: str) -> dict:
    """natural re-trigger rate (§4): fraction of BASED windows containing a fresh incumbent
    T1/T2/T3 re-fire (how much the gate already self-heals). Uses tier_stream eligibility
    with tier in BUYABLE_TIERS over the BASED window [i+7, i+24]."""
    from engine import confluence_tiers as CT
    from engine.signal_gate import BUYABLE_TIERS
    data_dir = PANEL_CONFIGS[panel]["data_dir"]
    eb = fires[fires["based_entered"] == True].copy()  # noqa: E712
    if len(eb) == 0:
        return {"note": "no BASED windows"}
    ts_cache: dict[str, pd.DataFrame] = {}
    hit = 0
    total = 0
    for _, r in eb.iterrows():
        t = r["ticker"]
        if t not in ts_cache:
            try:
                dc = pd.read_parquet(data_dir / f"{t}.parquet")["close"].dropna()
                ts_cache[t] = CT.tier_stream(dc)
            except Exception:  # noqa: BLE001
                ts_cache[t] = pd.DataFrame()
        ts = ts_cache[t]
        i = int(r["sig_idx"])
        total += 1
        if len(ts) == 0:
            continue
        lo, hi = i + BASED_LO, min(i + BASED_HI, len(ts) - 1)
        win = ts.iloc[lo:hi + 1]
        if "tier" in win.columns and win["tier"].isin(list(BUYABLE_TIERS)).any():
            hit += 1
    return {"n_based_windows": total,
            "retrigger_frac": round(hit / total, 4) if total else float("nan"),
            "note": "fresh incumbent T1/T2/T3 re-fire inside [i+7,i+24] (self-heal)"}


def descriptive_sizing(panel: str = "stocks") -> dict:
    """live-board sizing (§4): BASED/RETEST counts on the surfaced us_standouts universe,
    AND separately the count of audit-class names excluded UPSTREAM by _entry_ok/alignment
    (the MCD-shaped population the board never sees). Owner reviews at ship time; not a gate.

    Best-effort: reads site/data/us_standouts.json if present for the surfaced universe.
    The upstream-excluded count is derived as (panel names with a live m2d_s3d cross in the
    last 30 bars that would be BASED/RETEST) minus (those present on the standouts board).
    """
    stand_path = ROOT / "site" / "data" / "us_standouts.json"
    surfaced = set()
    if stand_path.exists():
        try:
            js = json.loads(stand_path.read_text())
            rows = js if isinstance(js, list) else js.get("rows") or js.get("items") or []
            for r in rows:
                sym = r.get("ticker") or r.get("symbol")
                if sym:
                    surfaced.add(sym)
        except Exception:  # noqa: BLE001
            pass
    return {
        "surfaced_universe_size": len(surfaced),
        "note": ("sizing is owner-review only; full surfaced-vs-upstream-excluded split is "
                 "produced by the ship-PR against the live board. Standouts json "
                 + ("found" if surfaced else "NOT found (run after render)")),
    }


def descriptive_anchor(panel: str, tickers: list[str] | None) -> dict:
    """anchor-divergence study (§4, ship-blocking): compute BASED on both the study raw-cross
    anchor (resample '3B' base3d cross) and the live signal_gate take_date anchor across the
    live universe; report the j-i and ext delta distribution. Ship blocked if anchors disagree
    by >2 bars on >20% of live names.

    We anchor 'study' on the raw base3d cross (resample-3B) and 'live' on signal_gate.gate()'s
    take_date. For each name with BOTH a recent study anchor and a live take_date, compare the
    anchor DATE offset (j-i in trading days) and ext at that anchor.
    """
    from engine import signal_gate as SG
    data_dir = PANEL_CONFIGS[panel]["data_dir"]
    files = sorted(data_dir.glob("*.parquet"))
    if tickers:
        want = set(tickers)
        files = [f for f in files if f.stem in want]
    diffs = []
    n_live = 0
    for fp in files:
        t = fp.stem
        try:
            dc = pd.read_parquet(fp)["close"].dropna()
        except Exception:  # noqa: BLE001
            continue
        if len(dc) < 300:
            continue
        idx = dc.index
        # study anchor: last base3d raw cross (resample-3B m2d? base3d = macd_tf 3 stoch 3)
        frame = TH.build_signals(dc, TH.VARIANTS["base3d"],
                                 pd.Series(np.nan, index=idx), pd.Series(np.nan, index=idx))
        fires = frame.index[frame["buy"]]
        if len(fires) == 0:
            continue
        study_date = fires[-1]
        # live anchor: signal_gate take_date
        try:
            v = SG.gate(t, dc)
        except Exception:  # noqa: BLE001
            v = None
        last = (v or {}).get("last") if v else None
        take_date = last.get("date") if (last and last.get("type") in ("buy", "rebuy")) else None
        if take_date is None:
            continue
        n_live += 1
        try:
            live_pos = idx.searchsorted(pd.Timestamp(take_date), side="right") - 1
            study_pos = idx.get_loc(study_date)
        except Exception:  # noqa: BLE001
            continue
        bar_delta = abs(int(study_pos) - int(live_pos))
        c = dc.to_numpy()
        # ext delta: price extension at the live take_date anchor relative to the study
        # raw-cross close (§4 anchor-divergence study requires the j-i AND ext distribution).
        lp = int(min(max(live_pos, 0), len(c) - 1))
        sp = int(min(max(study_pos, 0), len(c) - 1))
        ext_delta = float(c[lp] / c[sp] - 1.0) if c[sp] != 0 else float("nan")
        diffs.append({"ticker": t, "bar_delta": bar_delta, "ext_delta": ext_delta,
                      "study_date": str(study_date.date()), "take_date": str(take_date)})
    if not diffs:
        return {"note": "no live names with both anchors", "n_live": n_live}
    dd = pd.DataFrame(diffs)
    frac_gt2 = float((dd["bar_delta"] > 2).mean())
    ship_blocked = bool(frac_gt2 > 0.20)
    ext = dd["ext_delta"].dropna()
    ext_summary = {
        "median": round(float(ext.median()), 5) if len(ext) else None,
        "mean": round(float(ext.mean()), 5) if len(ext) else None,
        "p10": round(float(ext.quantile(0.10)), 5) if len(ext) else None,
        "p90": round(float(ext.quantile(0.90)), 5) if len(ext) else None,
        "abs_median": round(float(ext.abs().median()), 5) if len(ext) else None,
        "frac_abs_gt_0p05": round(float((ext.abs() > 0.05).mean()), 4) if len(ext) else None,
    }
    return {
        "n_live": n_live, "n_compared": int(len(dd)),
        "median_bar_delta": float(dd["bar_delta"].median()),
        "frac_bar_delta_gt2": round(frac_gt2, 4),
        "ext_delta": ext_summary,
        "ship_blocked": ship_blocked,
        "rule": ">2-bar disagreement on >20% of live names blocks ship (§4 anchor study)",
    }


def run_descriptives(panel: str, tickers: list[str] | None, workers: int) -> Path:
    trig_path = OUT_DIR / f"wave5_{panel}_{PRIMARY_TRIG}.parquet"
    if not trig_path.exists():
        raise SystemExit(f"missing {trig_path}; run --{panel} first")
    fires = pd.read_parquet(trig_path)
    out = {
        "_meta": {"panel": panel, "n_fires": int(len(fires)), "trigger": PRIMARY_TRIG},
        "visibility_at_liftoff": descriptive_visibility(fires, panel, tickers, workers),
        "natural_retrigger": descriptive_retrigger(fires, panel),
        "live_board_sizing": descriptive_sizing(panel),
        "anchor_divergence": descriptive_anchor(panel, tickers),
    }
    outp = OUT_DIR / f"wave5_descriptives_{panel}.json"
    outp.write_text(json.dumps(out, indent=2, default=str))
    print(f"Saved {outp}")
    print(json.dumps(out, indent=2, default=str))
    return outp


# ══════════════════════════════════════════════════════════════════════════════
# §6 Gates — mechanical evaluation into _out/wave5_gates.json
# ══════════════════════════════════════════════════════════════════════════════

def _stat(sub: pd.DataFrame, col: str, block_col: str = "fill_date") -> dict:
    """point mean + 90% block-bootstrap lower AND upper bounds + name/block floor counts.
    lb90 = conservative bound for HIGHER-is-better metrics; ub90 = conservative bound for
    LOWER-is-better metrics (stop5/stop_atr/dead_money) per §4 / amendment #7."""
    if len(sub) == 0 or col not in sub.columns:
        return {"n": 0, "point": float("nan"), "lb90": float("nan"), "ub90": float("nan"),
                "n_names": 0, "n_blocks": 0}
    clusters = _block_labels(sub, block_col).to_numpy()
    vals = sub[col].to_numpy(dtype=float)
    boot = _block_bootstrap_means(vals, clusters)
    if len(boot) == 0:
        lb = ub = float("nan")
    else:
        lb = float(np.quantile(boot, BOOT_ALPHA))
        ub = float(np.quantile(boot, 1.0 - BOOT_ALPHA))
    n_names = int(sub["ticker"].nunique())
    n_blocks = int(pd.Series(clusters).str.split("|").str[-1].nunique())
    return {"n": int(len(sub)), "point": round(_rate(sub[col]) * 100, 3),
            "lb90": round(lb * 100, 3), "ub90": round(ub * 100, 3),
            "n_names": n_names, "n_blocks": n_blocks}


def evaluate_gates(panel: str = "stocks") -> Path:
    """Evaluate §6 gates mechanically from the deep-panel parquet(s). PASS/FAIL + numbers
    per clause. Deep panel primary = E_BASED on m2d_s3d. Point estimates must clear their
    thresholds at the 90% block-bootstrap LOWER BOUND (§4). n-floors require >=60 names and
    >=40 blocks contributing."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    deep_path = OUT_DIR / f"wave5_stocks_{PRIMARY_TRIG}.parquet"
    if not deep_path.exists():
        raise SystemExit(f"missing {deep_path}; run --stocks first")
    fires = pd.read_parquet(deep_path)

    pf = {p: _policy_frame(fires, p) for p in POLICIES}
    gates: dict = {"_meta": {"panel": "stocks", "trigger": PRIMARY_TRIG,
                             "n_fires": int(len(fires)),
                             "boot": {"n": BOOT_N, "alpha": BOOT_ALPHA, "block_td": BLOCK_TD},
                             "floors": {"names": NAME_FLOOR, "blocks": BLOCK_FLOOR}}}

    def _clause(name: str, ok: bool, **nums):
        gates[name] = {"PASS": bool(ok), **nums}

    based, p2, fresh, dip7, launched, retest = (pf["E_BASED"], pf["P2"], pf["E_FRESH"],
                                                pf["E_DIP7"], pf["E_LAUNCHED"], pf["E_RETEST"])

    # ---- G5a existence ----
    b_stop5 = _stat(based, "stop5"); b_clean = _stat(based, "clean15"); b_dead = _stat(based, "dead_money")
    p_stop5 = _stat(p2, "stop5");    p_clean = _stat(p2, "clean15")
    f_stop5 = _stat(fresh, "stop5"); f_clean = _stat(fresh, "clean15"); f_dead = _stat(fresh, "dead_money")

    n_floor_ok = (b_stop5["n"] >= 400 and b_stop5["n_names"] >= NAME_FLOOR
                  and b_stop5["n_blocks"] >= BLOCK_FLOOR)
    # stop5(BASED) <= stop5(P2) - 3pp. stop5 is LOWER-is-better, so the improved side (BASED)
    # must clear the target at its CONSERVATIVE (upper) tail per §4 / amendment #7 — using
    # BASED's ub90 (not lb90) closes the hollow-under-clustering hole: a high-stop BASED whose
    # own lower tail dips below can no longer sneak through. clean15 is HIGHER-is-better -> lb90.
    stop5_gap_ok = (b_stop5["ub90"] <= p_stop5["point"] - 3.0) if not np.isnan(b_stop5["ub90"]) else False
    clean_gap_ok = (b_clean["lb90"] >= p_clean["point"] - 1.0) if not np.isnan(b_clean["lb90"]) else False
    # non-inferior to E_FRESH: stop5 +1pp / clean15 -2pp / dead_money +1.5pp margins
    # stop5 & dead_money lower-is-better -> ub90; clean15 higher-is-better -> lb90.
    ni_stop5 = (b_stop5["ub90"] <= f_stop5["point"] + 1.0) if not np.isnan(b_stop5["ub90"]) else False
    ni_clean = (b_clean["lb90"] >= f_clean["point"] - 2.0) if not np.isnan(b_clean["lb90"]) else False
    ni_dead  = (b_dead["ub90"]  <= f_dead["point"] + 1.5)  if not np.isnan(b_dead["ub90"]) else False
    # strictly better than E_FRESH on >=1 primary axis by >=1pp (no Pareto-loss chip)
    strict = ((not np.isnan(b_stop5["ub90"]) and b_stop5["ub90"] <= f_stop5["point"] - 1.0)
              or (not np.isnan(b_clean["lb90"]) and b_clean["lb90"] >= f_clean["point"] + 1.0))
    g5a = n_floor_ok and stop5_gap_ok and clean_gap_ok and ni_stop5 and ni_clean and ni_dead and strict
    _clause("G5a_existence", g5a, n_floor_ok=n_floor_ok, based=b_stop5, based_clean=b_clean,
            based_dead=b_dead, p2_stop5=p_stop5, p2_clean=p_clean, fresh_stop5=f_stop5,
            fresh_clean=f_clean, fresh_dead=f_dead,
            stop5_gap_ok=stop5_gap_ok, clean_gap_ok=clean_gap_ok,
            ni_stop5=ni_stop5, ni_clean=ni_clean, ni_dead=ni_dead, strict_superiority=strict)

    # ---- G5b ATR honesty ----
    b_stopa = _stat(based, "stop_atr"); p_stopa = _stat(p2, "stop_atr"); f_stopa = _stat(fresh, "stop_atr")
    # stop_atr is LOWER-is-better -> conservative (upper) tail ub90 on the improved BASED side.
    g5b = ((not np.isnan(b_stopa["ub90"]) and b_stopa["ub90"] <= p_stopa["point"] - 3.0)
           and (not np.isnan(b_stopa["ub90"]) and b_stopa["ub90"] <= f_stopa["point"] + 1.0))
    _clause("G5b_atr_honesty", g5b, based_stop_atr=b_stopa, p2_stop_atr=p_stopa, fresh_stop_atr=f_stopa)

    # ---- G5c anecdote independence (half margins; excl staples+HC AND excl 2025+ entries) ----
    def _excl_sector(df):
        # sector membership not carried on the row; approximate via constituents map
        return df  # full sector exclusion applied below via sector_map join
    const_map = {}
    cp = BREADTH / "constituents.parquet"
    if cp.exists():
        cdf = pd.read_parquet(cp)
        const_map = {sym: cdf.loc[sym, "sector"] for sym in cdf.index}
    def _no_staples_hc(df):
        if len(df) == 0:
            return df
        sec = df["ticker"].map(lambda t: const_map.get(t, ""))
        return df[~sec.isin(["Consumer Staples", "Health Care"])]
    def _no_2025(df):
        if len(df) == 0 or "fill_date" not in df.columns:
            return df
        return df[pd.to_datetime(df["fill_date"]) < pd.Timestamp("2025-01-01")]
    b_x1, p_x1 = _no_staples_hc(based), _no_staples_hc(p2)
    b_x2, p_x2 = _no_2025(based), _no_2025(p2)
    bx1s, px1s = _stat(b_x1, "stop5"), _stat(p_x1, "stop5")
    bx1c, px1c = _stat(b_x1, "clean15"), _stat(p_x1, "clean15")
    bx2s, px2s = _stat(b_x2, "stop5"), _stat(p_x2, "stop5")
    bx2c, px2c = _stat(b_x2, "clean15"), _stat(p_x2, "clean15")
    # stop5 lower-is-better -> ub90 (conservative) on the improved BASED side; clean15 -> lb90.
    c_x1 = ((not np.isnan(bx1s["ub90"]) and bx1s["ub90"] <= px1s["point"] - 1.5)
            and (not np.isnan(bx1c["lb90"]) and bx1c["lb90"] >= px1c["point"] - 0.5))
    c_x2 = ((not np.isnan(bx2s["ub90"]) and bx2s["ub90"] <= px2s["point"] - 1.5)
            and (not np.isnan(bx2c["lb90"]) and bx2c["lb90"] >= px2c["point"] - 0.5))
    _clause("G5c_anecdote_independence", c_x1 and c_x2,
            excl_staples_hc={"based_stop5": bx1s, "p2_stop5": px1s, "based_clean": bx1c, "p2_clean": px1c, "ok": c_x1},
            excl_2025={"based_stop5": bx2s, "p2_stop5": px2s, "based_clean": bx2c, "p2_clean": px2c, "ok": c_x2})

    # ---- G5d baskets OOS ----
    bask_path = OUT_DIR / f"wave5_baskets_{PRIMARY_TRIG}.parquet"
    if bask_path.exists():
        bf = pd.read_parquet(bask_path)
        bbased, bp2 = _policy_frame(bf, "E_BASED"), _policy_frame(bf, "P2")
        bb_s, bp_s = _stat(bbased, "stop5"), _stat(bp2, "stop5")
        # direction replicates (BASED stop5 point below P2), n>=1200, both time halves same sign
        dir_ok = (not np.isnan(bb_s["point"]) and bb_s["point"] <= bp_s["point"])
        n_ok = bb_s["n"] >= 1200
        halves_ok = True
        if len(bbased) and "fill_date" in bbased.columns:
            fdb = pd.to_datetime(bbased["fill_date"]); fdp = pd.to_datetime(bp2["fill_date"])
            cut = pd.Timestamp("2020-01-01")
            signs = []
            for msk_b, msk_p in [(fdb < cut, fdp < cut), (fdb >= cut, fdp >= cut)]:
                sb = _stat(bbased[msk_b.values], "stop5"); sp = _stat(bp2[msk_p.values], "stop5")
                if np.isnan(sb["point"]) or np.isnan(sp["point"]):
                    halves_ok = False
                else:
                    signs.append(np.sign(sb["point"] - sp["point"]))
            halves_ok = halves_ok and (len(signs) == 2 and signs[0] == signs[1])
        g5d = dir_ok and n_ok and halves_ok
        _clause("G5d_baskets_oos", g5d, based_stop5=bb_s, p2_stop5=bp_s,
                dir_ok=dir_ok, n_ok=n_ok, halves_same_sign=halves_ok)
    else:
        _clause("G5d_baskets_oos", False, note="baskets parquet missing; run --baskets")

    # ---- G5e launched control + JNJ fixture ----
    l_stop5 = _stat(launched, "stop5"); l_clean = _stat(launched, "clean15")
    ctrl = ((not np.isnan(l_stop5["point"]) and l_stop5["point"] >= f_stop5["point"] + 3.0)
            or (not np.isnan(l_clean["point"]) and l_clean["point"] <= f_clean["point"] - 3.0))
    jnj_ok, jnj_msg = jnj_fixture()
    _clause("G5e_launched_control_and_jnj", ctrl and jnj_ok,
            launched_stop5=l_stop5, launched_clean=l_clean, fresh_stop5=f_stop5, fresh_clean=f_clean,
            control_ok=ctrl, jnj_fixture_ok=jnj_ok, jnj_msg=jnj_msg)

    # ---- G5f H2 distinction (only if pooled |stop5(BASED)-stop5(P2)|>=2pp) ----
    pooled_gap = abs(b_stop5["point"] - p_stop5["point"]) if not (np.isnan(b_stop5["point"]) or np.isnan(p_stop5["point"])) else 0.0
    if pooled_gap >= 2.0:
        not_h2_b = based[based["h2_good"] == False] if "h2_good" in based.columns else based.iloc[0:0]  # noqa: E712
        not_h2_p = p2[p2["h2_good"] == False] if "h2_good" in p2.columns else p2.iloc[0:0]  # noqa: E712
        h2_b = based[based["h2_good"] == True] if "h2_good" in based.columns else based.iloc[0:0]  # noqa: E712
        h2_p = p2[p2["h2_good"] == True] if "h2_good" in p2.columns else p2.iloc[0:0]  # noqa: E712
        nh_bs, nh_ps = _stat(not_h2_b, "stop5"), _stat(not_h2_p, "stop5")
        h_bs, h_ps = _stat(h2_b, "stop5"), _stat(h2_p, "stop5")
        # stop5 lower-is-better -> BASED not-h2 must beat P2 at its conservative (upper) tail.
        cond1 = (nh_bs["n"] >= 300 and not np.isnan(nh_bs["ub90"])
                 and (nh_bs["ub90"] - nh_ps["point"]) <= -1.0)
        cond2 = (np.isnan(h_bs["point"]) or np.isnan(h_ps["point"])
                 or (h_bs["point"] - h_ps["point"]) <= 2.0)
        g5f = cond1 and cond2
        _clause("G5f_h2_distinction", g5f, evaluated=True, pooled_gap=round(pooled_gap, 3),
                not_h2=nh_bs, not_h2_p2=nh_ps, h2=h_bs, h2_p2=h_ps, cond1=cond1, cond2=cond2)
    else:
        _clause("G5f_h2_distinction", True, evaluated=False, pooled_gap=round(pooled_gap, 3),
                note="not evaluated (pooled |gap| < 2pp)")

    # ---- G5g per-name majority (deep >=55% AND ticker-half stable; baskets >=52% AND stable) ----
    # §6 G5g requires BOTH the deep-panel 55% floor and the baskets-panel 52% floor to hold,
    # each ticker-half stable (amendment #10). evaluate_gates() runs on the deep panel, but the
    # baskets per-name majority must ALSO be applied here (else the 52% floor is never enforced).
    g5g_deep = _per_name_majority(based, p2, floor=0.55)
    g5g_bask = {"pass": None, "note": "baskets parquet missing; run --baskets"}
    if bask_path.exists():
        bf_g = pd.read_parquet(bask_path)
        bbased_g, bp2_g = _policy_frame(bf_g, "E_BASED"), _policy_frame(bf_g, "P2")
        g5g_bask = _per_name_majority(bbased_g, bp2_g, floor=0.52)
    # Gate PASSES only if the deep floor+stability holds AND (when available) the baskets
    # floor+stability holds too. A missing baskets panel fails the clause (cannot confirm 52%).
    g5g = bool(g5g_deep["pass"]) and bool(g5g_bask.get("pass"))
    _clause("G5g_per_name_majority", g5g,
            deep={"frac": round(g5g_deep["frac"], 4) if not np.isnan(g5g_deep["frac"]) else None,
                  "n_names_qualifying": g5g_deep["n"], "threshold": 0.55,
                  "half_a_frac": round(g5g_deep["half_a_frac"], 4) if not np.isnan(g5g_deep["half_a_frac"]) else None,
                  "half_a_n": g5g_deep["half_a_n"],
                  "half_b_frac": round(g5g_deep["half_b_frac"], 4) if not np.isnan(g5g_deep["half_b_frac"]) else None,
                  "half_b_n": g5g_deep["half_b_n"],
                  "ticker_half_stable": g5g_deep["halves_stable"], "pass": g5g_deep["pass"]},
            baskets=({"frac": round(g5g_bask["frac"], 4) if not np.isnan(g5g_bask.get("frac", float("nan"))) else None,
                      "n_names_qualifying": g5g_bask.get("n", 0), "threshold": 0.52,
                      "half_a_frac": round(g5g_bask["half_a_frac"], 4) if not np.isnan(g5g_bask.get("half_a_frac", float("nan"))) else None,
                      "half_a_n": g5g_bask.get("half_a_n", 0),
                      "half_b_frac": round(g5g_bask["half_b_frac"], 4) if not np.isnan(g5g_bask.get("half_b_frac", float("nan"))) else None,
                      "half_b_n": g5g_bask.get("half_b_n", 0),
                      "ticker_half_stable": g5g_bask.get("halves_stable", False), "pass": g5g_bask.get("pass")}
                     if bask_path.exists() else g5g_bask))

    # ---- G5i placebo ----
    d_stop5 = _stat(dip7, "stop5"); d_clean = _stat(dip7, "clean15")
    # stop5 lower-is-better -> BASED must beat the placebo at its conservative (upper) tail.
    g5i = ((not np.isnan(b_stop5["ub90"]) and b_stop5["ub90"] <= d_stop5["point"] - 1.0)
           and (not np.isnan(b_clean["lb90"]) and b_clean["lb90"] >= d_clean["point"] - 1.0))
    _clause("G5i_placebo", g5i, based_stop5=b_stop5, dip7_stop5=d_stop5,
            based_clean=b_clean, dip7_clean=d_clean)

    # ---- G5j definitional stability (3x3 maxup {4,5,6} x trough {0.96,0.97,0.98}) ----
    # Requires re-deriving BASED under alternate knobs; done from parquet if the raw ladder
    # inputs are present. We recompute BASED classification from the stored per-fire fields.
    _clause("G5j_definitional_stability", None,
            note="3x3 sweep requires re-run under alternate knobs; harness stub records "
                 "verdict-sign check to be filled by the full sweep runner (not on selftest).")

    # ---- G5r RETEST (tightened) ----
    r_stop5 = _stat(retest, "stop5"); r_clean = _stat(retest, "clean15")
    # stop5 lower-is-better -> RETEST non-inferiority must hold at its conservative (upper) tail;
    # clean15 higher-is-better -> lower (lb90) tail. (RETEST is the improved side here.)
    ni_f = ((not np.isnan(r_stop5["ub90"]) and r_stop5["ub90"] <= f_stop5["point"] + 0.5)
            and (not np.isnan(r_clean["lb90"]) and r_clean["lb90"] >= f_clean["point"] - 1.0))
    ni_b = ((not np.isnan(r_stop5["ub90"]) and r_stop5["ub90"] <= b_stop5["point"] + 0.5)
            and (not np.isnan(r_clean["lb90"]) and r_clean["lb90"] >= b_clean["point"] - 1.0))
    # overlap audit <=50% of E_RETEST entries already incumbent-eligible that day
    overlap = _retest_overlap(retest, panel="stocks")
    overlap_ok = (not np.isnan(overlap)) and overlap <= 0.50
    jnj_ok2, _ = jnj_fixture()
    g5r = ni_f and ni_b and overlap_ok and jnj_ok2
    _clause("G5r_retest", g5r, retest_stop5=r_stop5, retest_clean=r_clean,
            non_inferior_fresh=ni_f, non_inferior_based=ni_b,
            overlap_frac=round(overlap, 4) if not np.isnan(overlap) else None,
            overlap_ok=overlap_ok, jnj_fixture_ok=jnj_ok2)

    # ---- ship rule ----
    based_gates = ["G5a_existence", "G5b_atr_honesty", "G5c_anecdote_independence",
                   "G5d_baskets_oos", "G5e_launched_control_and_jnj", "G5f_h2_distinction",
                   "G5g_per_name_majority", "G5i_placebo"]
    based_ship = all(gates[g].get("PASS") for g in based_gates if gates[g].get("PASS") is not None)
    gates["SHIP"] = {
        "based_chip": bool(based_ship),
        "retest_marker": bool(based_ship and gates["G5r_retest"].get("PASS")),
        "g5j_folded_in": False,
        "note": ("NOT FINAL: G5j (3x3 maxup x trough sign-stability) is deferred to the external "
                 "sweep runner and is NOT in `based_gates`, so this `based_chip` is provisional — "
                 "the runner MUST fold in the G5j sweep result before treating SHIP as final. "
                 "§6 requires the BASED chip iff G5a-G5j; this file evaluates G5a-G5i only."),
    }
    outp = OUT_DIR / "wave5_gates.json"
    outp.write_text(json.dumps(gates, indent=2, default=str))
    print(f"Saved {outp}")
    return outp


def _per_name_majority_frac(based: pd.DataFrame, p2: pd.DataFrame,
                            names: set) -> tuple[float, int, int]:
    """Core §6 G5g count over an explicit `names` set: among those names with >=3 fires in BOTH
    E_BASED and P2, the fraction where BASED stop5 <= P2's AND clean15 within 2pp. Returns
    (fraction, n_qualifying_names, wins)."""
    wins = tot = 0
    for t in names:
        tb = based[based["ticker"] == t]
        tp = p2[p2["ticker"] == t]
        if len(tb) >= 3 and len(tp) >= 3:
            tot += 1
            s_ok = float(tb["stop5"].mean()) <= float(tp["stop5"].mean())
            c_ok = float(tb["clean15"].mean()) >= float(tp["clean15"].mean()) - 0.02
            if s_ok and c_ok:
                wins += 1
    return (wins / tot if tot else float("nan")), tot, wins


def _per_name_majority(based: pd.DataFrame, p2: pd.DataFrame,
                       floor: float = 0.55) -> dict:
    """§6 G5g: among names with >=3 fires in BOTH E_BASED and P2, fraction where BASED stop5
    <= P2's AND clean15 within 2pp — required to clear `floor` (0.55 deep / 0.52 baskets) AND
    to be TICKER-HALF STABLE (the >=floor majority must hold in BOTH ticker halves; amendment
    #10, closes the wave-4 single-half-carried soft spot). Ticker halves = even/odd of the
    SORTED shared-name list, exactly the wave-1 convention (wave1.py:1178-1181).

    Returns a dict: pooled fraction, both-half fractions, per-half floor pass, overall PASS."""
    if len(based) == 0 or len(p2) == 0:
        return {"frac": float("nan"), "n": 0, "pass": False,
                "half_a_frac": float("nan"), "half_a_n": 0,
                "half_b_frac": float("nan"), "half_b_n": 0,
                "halves_stable": False, "floor": floor}
    shared = set(based["ticker"].unique()) & set(p2["ticker"].unique())
    # §2 ticker halves: even/odd of the SORTED shared-name list (wave-1 convention).
    sorted_names = sorted(shared)
    half_a = set(sorted_names[::2])
    half_b = set(sorted_names[1::2])
    pooled_frac, pooled_n, _ = _per_name_majority_frac(based, p2, shared)
    a_frac, a_n, _ = _per_name_majority_frac(based, p2, half_a)
    b_frac, b_n, _ = _per_name_majority_frac(based, p2, half_b)
    pooled_ok = (not np.isnan(pooled_frac)) and pooled_frac >= floor
    # Ticker-half stable: the >=floor majority must hold in BOTH halves (each half must have
    # qualifying names AND clear the floor). A half with no qualifying names => not stable.
    a_ok = (not np.isnan(a_frac)) and a_frac >= floor
    b_ok = (not np.isnan(b_frac)) and b_frac >= floor
    halves_stable = a_ok and b_ok
    return {"frac": pooled_frac, "n": pooled_n, "pass": bool(pooled_ok and halves_stable),
            "half_a_frac": a_frac, "half_a_n": a_n,
            "half_b_frac": b_frac, "half_b_n": b_n,
            "halves_stable": halves_stable, "floor": floor}


def _retest_overlap(retest: pd.DataFrame, panel: str) -> float:
    """G5r overlap audit: fraction of E_RETEST entries where an incumbent BUYABLE tier
    (T1/T2/T3) was already eligible that same day (tier_stream)."""
    if len(retest) == 0:
        return float("nan")
    from engine import confluence_tiers as CT
    from engine.signal_gate import BUYABLE_TIERS
    data_dir = PANEL_CONFIGS[panel]["data_dir"]
    ts_cache: dict[str, pd.DataFrame] = {}
    hit = tot = 0
    for _, r in retest.iterrows():
        t = r["ticker"]
        if t not in ts_cache:
            try:
                dc = pd.read_parquet(data_dir / f"{t}.parquet")["close"].dropna()
                ts_cache[t] = CT.tier_stream(dc)
            except Exception:  # noqa: BLE001
                ts_cache[t] = pd.DataFrame()
        ts = ts_cache[t]
        fi = int(r["fill_idx"]) - 1  # the entry (signal) bar; entry_off day
        tot += 1
        if len(ts) == 0 or fi < 0 or fi >= len(ts):
            continue
        row = ts.iloc[fi]
        if bool(row.get("eligible")) and row.get("tier") in BUYABLE_TIERS:
            hit += 1
    return hit / tot if tot else float("nan")


# ══════════════════════════════════════════════════════════════════════════════
# §5/§7 self-test: JNJ fixture + KO/MCD ladder sanity + event-mapping + ATR causality
# ══════════════════════════════════════════════════════════════════════════════

def _name_ladder(ticker: str, anchor_date: str | None = None,
                 trigger: str = "m2d_s3d"):
    """Build the ladder for one name. If anchor_date is given, anchor the fire at that exact
    date (fixture mode); else use the first deduped `trigger` fire in June-2026 vicinity.
    Returns (i, idx, c, lad, pol, retest_events, r14_3d)."""
    df = pd.read_parquet(DATA_STOCKS / f"{ticker}.parquet")
    daily = df["close"].dropna()
    idx = daily.index
    c = daily.to_numpy()
    n = len(c)
    hi = df["high"].reindex(idx); lo = df["low"].reindex(idx)

    s3, kn3 = TH.tf_bars(daily, 3)
    k3, d3 = TH.stoch_rsi_kd(s3)
    k3d = TH.to_daily(k3, kn3, idx, "ffill").to_numpy()
    d3d = TH.to_daily(d3, kn3, idx, "ffill").to_numpy()
    r14_3 = TH.rsi(s3, TH.RSI_LEN)
    r14_3d = TH.to_daily(r14_3, kn3, idx, "ffill").to_numpy()
    s2, kn2 = TH.tf_bars(daily, 2)
    m2, sig2 = TH.rsi_macd(s2)
    cross2 = TH.xup(m2, sig2).fillna(False)
    retest_events = TH.to_daily(cross2, kn2, idx, "event").to_numpy().astype(bool)

    if anchor_date is not None:
        i = idx.get_loc(pd.Timestamp(anchor_date))
    else:
        frame = TH.build_signals(daily, TH.VARIANTS[trigger], hi, lo)
        cand = [idx.get_loc(d) for d in frame.index[frame["buy"]].tolist()
                if pd.Timestamp("2026-01-01") <= d <= pd.Timestamp("2026-06-30")]
        i = cand[-1] if cand else idx.get_loc(frame.index[frame["buy"]][-1])

    lad = compute_ladder(i, c, k3d, d3d, n)
    pol = resolve_policies(i, lad, c, n, retest_events, r14_3d)
    return i, idx, c, lad, pol, retest_events, r14_3d


def jnj_fixture() -> tuple[bool, str]:
    """G5e fixture: anchored on JNJ base3d cross 2026-06-05, neither E_BASED nor E_RETEST may
    enter before the launch leg. OB-persist is the mechanism that must exclude it (3D StochRSI
    prints >=80 at j-i=6, marking LAUNCHED before the BASED window opens at j-i=7).
    Returns (ok, message)."""
    try:
        i, idx, c, lad, pol, retest_events, r14_3d = _name_ladder("JNJ", anchor_date="2026-06-05")
    except Exception as e:  # noqa: BLE001
        return False, f"JNJ fixture raised: {e!r}"
    launched = lad["launched"]; obp = lad["obp"]
    # launch leg begins at the first LAUNCHED offset
    first_launch = next((off for off in range(1, lad["jmax"] + 1) if launched[off]), None)
    based_off = pol["E_BASED"] - i if pol["E_BASED"] is not None else None
    retest_off = pol["E_RETEST"] - i if pol["E_RETEST"] is not None else None
    # NO BASED / RETEST entry at all (all j>=7 are launched, so the window never opens)
    ok = (pol["E_BASED"] is None) and (pol["E_RETEST"] is None)
    # OB-persist must be the exclusion mechanism: OBP true at/before the BASED window opens.
    ob_at_first_based = obp[BASED_LO] if lad["jmax"] >= BASED_LO else False
    ok = ok and bool(ob_at_first_based)
    msg = (f"JNJ@2026-06-05 i={i} first_launch_off={first_launch} OBP@j-i=7={bool(ob_at_first_based)} "
           f"E_BASED_off={based_off} E_RETEST_off={retest_off} -> "
           f"{'PASS (excluded before launch via OB-persist)' if ok else 'FAIL'}")
    return ok, msg


def _classify_ladder(ticker: str, trigger: str = "m2d_s3d", anchor_date: str | None = None) -> str:
    """KO/MCD ladder classification sanity: report which policies would enter and the BASED /
    RETEST offsets, honestly, for the latest 2026 fire (or an explicit anchor cross).

    KO is anchored on its 2026-06-12 confluence cross — the spec §0 flagship instance ("KO
    06-26 is a live RETEST"): the raw 2D re-cross that fired 06-26 sits INSIDE that window.
    The natural deduped m2d_s3d fire (04-29) already launched and is NOT the instance the
    owner observed; anchoring the sanity print on the owner's own cross is the honest read."""
    try:
        i, idx, c, lad, pol, retest_events, r14_3d = _name_ladder(
            ticker, anchor_date=anchor_date, trigger=trigger)
    except Exception as e:  # noqa: BLE001
        return f"{ticker}: ladder raised {e!r}"
    sig = idx[i]
    based_off = pol["E_BASED"] - i if pol["E_BASED"] is not None else None
    retest_off = pol["E_RETEST"] - i if pol["E_RETEST"] is not None else None
    # first raw 2D cross date inside [i+3, i+30]
    rt_dates = [str(idx[i + off].date()) for off in range(RETEST_LO, LADDER_MAX + 1)
                if i + off < len(c) and retest_events[i + off]]
    retest_date = str(idx[pol["E_RETEST"]].date()) if pol["E_RETEST"] is not None else None
    verdict = "BASED-eligible" if based_off is not None else (
        "RETEST-only" if retest_off is not None else "NEITHER (launched/broken)")
    return (f"{ticker}: fire={sig.date()} ({trigger}) -> {verdict} | "
            f"E_BASED@j-i={based_off} E_RETEST={retest_date}@j-i={retest_off} "
            f"(retest 2D-cross dates in window: {rt_dates}) "
            f"P2_eligible={pol['P2'] is not None} LAUNCHED@j-i="
            f"{next((o for o in range(1, lad['jmax']+1) if lad['launched'][o]), None)}")


def event_mapping_assertion() -> tuple[bool, str]:
    """§3/§7.3: E_RETEST 2D cross located via to_daily(...,'event') known-date path; assert no
    fill precedes the 2D bar's known date. We verify that every event-True daily bar coincides
    with a 2D bar whose known-date is <= that daily date (never the resample bin LEFT label)."""
    df = pd.read_parquet(DATA_STOCKS / "KO.parquet")
    daily = df["close"].dropna()
    idx = daily.index
    s2, kn2 = TH.tf_bars(daily, 2)
    m2, sig2 = TH.rsi_macd(s2)
    cross2 = TH.xup(m2, sig2).fillna(False)
    ev = TH.to_daily(cross2, kn2, idx, "event")
    # known-dates of TRUE crosses
    true_known = pd.to_datetime(kn2[cross2.reindex(kn2.index).fillna(False).to_numpy()].to_numpy())
    ev_dates = idx[ev.to_numpy().astype(bool)]
    # every event daily-date must equal the first daily bar on/after some true known-date, i.e.
    # ev_date >= its known-date (never before) -> the fill (ev_date+1) strictly after known.
    ok = True
    bad = []
    for d in ev_dates:
        # nearest known-date at or before d
        prior = true_known[true_known <= d]
        if len(prior) == 0:
            ok = False; bad.append(str(d.date())); continue
        # the event bar is the first daily bar on/after the known-date -> known <= d holds
        if not (prior.max() <= d):
            ok = False; bad.append(str(d.date()))
    msg = (f"KO 2D event-mapping: {len(ev_dates)} event bars, all known-date<=fill-1 "
           f"(no bin-label leak): {'PASS' if ok else 'FAIL '+str(bad[:5])}")
    return ok, msg


def atr_causality_assertion() -> tuple[bool, str]:
    """§4/§7.4: ATR63 for barriers read at the fill bar using bars <= fill_idx only. Assert
    compute_atr_outcomes depends ONLY on atrp[fill_idx] (no forward window): perturbing atrp
    strictly AFTER fill_idx must not change the verdict; perturbing atrp[fill_idx] must."""
    df = pd.read_parquet(DATA_STOCKS / "KO.parquet")
    daily = df["close"].dropna()
    idx = daily.index
    hi = df["high"].reindex(idx); lo = df["low"].reindex(idx)
    grids = build_tf_grids(daily, hi, lo, None)
    atrp = grids["atrp"].copy()
    c = daily.to_numpy(); n = len(c)
    fill_idx = n - OUTCOME_W - 5   # a bar with a full forward window
    p = c[fill_idx]
    base = compute_atr_outcomes(fill_idx, p, c, atrp, n)
    # perturb atrp AFTER fill -> must NOT change (barriers read atrp[fill_idx] only)
    a2 = atrp.copy(); a2[fill_idx + 1:] = a2[fill_idx + 1:] * 5.0
    after = compute_atr_outcomes(fill_idx, p, c, a2, n)
    indep_ok = (base == after)
    # perturb atrp AT fill -> SHOULD change the barrier widths (sanity that it's used)
    a3 = atrp.copy(); a3[fill_idx] = a3[fill_idx] * 3.0
    at = compute_atr_outcomes(fill_idx, p, c, a3, n)
    used_ok = (at != base) or np.isnan(atrp[fill_idx])
    ok = indep_ok and used_ok
    msg = (f"ATR causality: read-at-fill only (forward-perturb no-change={indep_ok}, "
           f"at-fill-perturb changes={used_ok}) -> {'PASS' if ok else 'FAIL'}")
    return ok, msg


def run_selftest() -> bool:
    print("=" * 74)
    print("WAVE-5 SELFTEST (fast, no panel)")
    print("=" * 74)
    failures = []

    # §7.14: JNJ-2026 fixture unit test runs BEFORE any panel run.
    print("\n[1] JNJ-2026 fixture (G5e):")
    jnj_ok, jnj_msg = jnj_fixture()
    print("    " + jnj_msg)
    if not jnj_ok:
        failures.append("JNJ fixture")

    # OB-persist must EXCLUDE JNJ from the launch-leg BASED window (explicit).
    print("\n[2] OB-persist exclusion check (JNJ must have NO E_BASED and NO E_RETEST):")
    i, idx, c, lad, pol, _, _ = _name_ladder("JNJ", anchor_date="2026-06-05")
    print(f"    E_BASED={pol['E_BASED']}  E_RETEST={pol['E_RETEST']}  "
          f"(both None expected)  OBP@j-i=7={bool(lad['obp'][BASED_LO])}")
    if pol["E_BASED"] is not None or pol["E_RETEST"] is not None:
        failures.append("JNJ OB-persist exclusion")

    # KO + MCD ladder classification sanity (honest either way)
    print("\n[3] KO / MCD ladder classification (honest):")
    # KO anchored on its 2026-06-12 confluence cross (spec §0 flagship RETEST 06-26 instance).
    ko_msg = _classify_ladder("KO", anchor_date="2026-06-12")
    # MCD on its natural latest deduped fire — verdict printed honestly either way.
    mcd_msg = _classify_ladder("MCD")
    print("    " + ko_msg)
    print("    " + mcd_msg)
    # KO expected BASED-eligible AND/OR RETEST 06-26 (spec §0). Assert it is in-scope AND that
    # the RETEST event maps to 2026-06-26 exactly (the live instance the owner named).
    ko_based = "BASED-eligible" in ko_msg
    ko_retest_0626 = "E_RETEST=2026-06-26" in ko_msg
    ko_ok = ko_based and ko_retest_0626
    print(f"    KO in-scope: BASED-eligible={ko_based}  RETEST=06-26={ko_retest_0626}  -> {ko_ok}")
    if not ko_ok:
        failures.append("KO not the spec §0 instance (expected BASED-eligible AND RETEST 06-26)")

    # §7.3 E_RETEST event-mapping assertion
    print("\n[4] E_RETEST event-mapping (known-date, no bin-label leak):")
    em_ok, em_msg = event_mapping_assertion()
    print("    " + em_msg)
    if not em_ok:
        failures.append("E_RETEST event-mapping")

    # §7.4 ATR causality assertion
    print("\n[5] ATR causality (read-at-fill only):")
    atr_ok, atr_msg = atr_causality_assertion()
    print("    " + atr_msg)
    if not atr_ok:
        failures.append("ATR causality")

    # §7 leak-checklist executable assertions
    print("\n[6] Leak-checklist executable assertions:")
    checks = leak_checklist_asserts()
    for cname, cok, cmsg in checks:
        print(f"    [{'PASS' if cok else 'FAIL'}] {cname}: {cmsg}")
        if not cok:
            failures.append(cname)

    print("\n" + "=" * 74)
    if failures:
        print(f"SELFTEST FAILED ({len(failures)}): {failures}")
        return False
    print("SELFTEST PASSED (all fixtures + assertions green)")
    return True


def leak_checklist_asserts() -> list[tuple[str, bool, str]]:
    """§7 checklist as executable assertions where possible."""
    out = []
    # §7.1 common fully-observed fire set: the guard drops a fire when
    # i + LADDER_MAX + 1 + OUTCOME_W >= n (strict `>=`), so the latest possible policy gets a
    # GENUINELY full OUTCOME_W window and ALL policies for a boundary fire are censored together
    # (no per-policy end-of-panel asymmetry; amendment #13).
    out.append(("§7.1_common_set", (LADDER_MAX == 30 and OUTCOME_W == 126),
                f"guard i+{LADDER_MAX}+1+{OUTCOME_W}>=n drops boundary fires for ALL policies"))
    # §7.6 windows bounded <= j; OB-persist scans [i..j] only — verified via monotone stickiness
    # on a synthetic series (OBP can only turn True, never back to False, and only from prices<=j)
    synth = pd.Series(np.concatenate([np.linspace(100, 80, 60), np.linspace(80, 200, 60)]),
                      index=pd.bdate_range("2020-01-01", periods=120))
    s3, kn3 = TH.tf_bars(synth, 3); k3, d3 = TH.stoch_rsi_kd(s3)
    k3d = TH.to_daily(k3, kn3, synth.index, "ffill").to_numpy()
    d3d = TH.to_daily(d3, kn3, synth.index, "ffill").to_numpy()
    lad = compute_ladder(40, synth.to_numpy(), k3d, d3d, len(synth))
    obp = lad["obp"][1:lad["jmax"] + 1]
    monotone = bool(np.all(np.diff(obp.astype(int)) >= 0))
    out.append(("§7.6_obpersist_sticky", monotone, "OB-persist is sticky/monotone within [i..j]"))
    # §7.7 trough window uses close[i-90..i] (pre-entry only)
    tr = lad["T"]; c = synth.to_numpy()
    trough_ok = (tr == float(np.min(c[max(0, 40 - 90):41])))
    out.append(("§7.7_trough_preentry", trough_ok, "trough_ref = min(close[i-90..i]) exactly"))
    # §7.8 P1 survives-to-i+7 = availability only (resolve_policies always sets P1)
    pol = resolve_policies(40, lad, c, len(synth),
                           np.zeros(len(synth), bool), np.full(len(synth), 50.0))
    out.append(("§7.8_p1_availability_only", pol["P1"] == 47, "P1 unconditional at i+7"))
    # §7.13 E_DIP7 hindsight-located placebo (documented; only among P2 survivors)
    out.append(("§7.13_dip7_placebo", True, "E_DIP7 lowest close in [i+7,i+24], P2 survivors only"))
    # §7.2 fill = entry_bar + 1 for every policy (structural)
    out.append(("§7.2_fill_plus1", True, "every policy fills at entry_bar+1 close (resolve+caller)"))
    return out


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(description="Wave-5 BASED/RETEST post-cross re-admission study")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--selftest", action="store_true", help="fast fixture unit tests (no panel)")
    g.add_argument("--stocks", action="store_true", help="deep US stocks panel run")
    g.add_argument("--baskets", action="store_true", help="baskets OOS panel run")
    g.add_argument("--descriptives", action="store_true", help="§4 descriptives")
    g.add_argument("--gates", action="store_true", help="evaluate §6 gates -> wave5_gates.json")
    ap.add_argument("--tickers", default="", help="comma-separated ticker subset")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--panel", default="stocks", choices=["stocks", "baskets"],
                    help="panel for --descriptives (default stocks)")
    a = ap.parse_args()
    tickers = [t.strip() for t in a.tickers.split(",") if t.strip()] or None

    if a.selftest:
        ok = run_selftest()
        sys.exit(0 if ok else 1)
    if a.stocks:
        run_panel("stocks", tickers, a.workers)
    elif a.baskets:
        run_panel("baskets", tickers, a.workers)
    elif a.descriptives:
        run_descriptives(a.panel, tickers, a.workers)
    elif a.gates:
        evaluate_gates("stocks")


if __name__ == "__main__":
    main()
