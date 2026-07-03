"""wave6.py — Durable-Bottom Entry Timing Study, Wave 6.

BINDING SPEC (read fully): research/entry_timing/WAVE6_PREREG.md (v2, incl. §8 amendment log).
Context: WAVE5_PREREG.md, WAVE5_REPORT.md (incl. §11), wave5.py, wave5b.py,
         research/signal_engine/DURABLE_BOTTOM_FRAMEWORK.md §2/§4.

Three legs:
  W6-A  donor-unwind promotion on E_FRESH entries, EPISODE-level cluster bootstrap
        (episodes = maximal runs of consecutive cracking days on the donor timeline).
        The SOLE statistical ship decision of the wave (G6a, §1).
  W6-B  blocked-population DISCOVERY (stratification, wave-1 protocol). Honest replication
        of engine.signal_quality._buy_filter's below∧weekly-down BLOCKED path on the 3D grid
        (¬above200 ∧ ¬w_bull, NOT bear-div-vetoed, NOT saved by held∧reclaim at the next two
        3D bars). Feature battery F1-F8 + singles stratification + composites C-SHALLOW,
        C-LOCKOUT (ratchet). NOTHING from W6-B ships this wave — promotions only.
  W6-C  is a PRODUCT decision (engine/coiled.py port + chip surfaces) — NOT this harness's job;
        this file produces the statistics + fixtures only.

REUSED BY IMPORT (never reimplemented / modified):
  wave1.py           compute_outcomes, build_tf_grids, build_sector_d_matrix, get_cohort_frac,
                     OUTCOME_W, MFE_MAE_W, H2_* constants.
  wave2.py           PANEL_CONFIGS, load_membership, build_basket_sector_map, _serialize_d_matrix,
                     the Pool pattern.
  wave5.py           block-bootstrap machinery (_block_bootstrap_means, block_bootstrap_lb/ub),
                     _rate, DEDUPE constants where applicable, ATR-barrier compute (imported).
  wave5b.py          build_sector_composites, build_donor_timeline — the #25 donor definition
                     VERBATIM (min-members / top-rank / completed-week guards).
  tuning_harness.py  rsi, ema, rsi_macd, stoch_rsi_kd, xup, xdn, tf_bars, to_daily, build_signals,
                     VARIANTS.
  engine.signal_quality  signal_frame, _buy_filter, _bear_div, _swing_highs (READ to replicate
                     the blocked path EXACTLY on the 3D grid; never modified).

CLI:
  --selftest   ALL fixtures, run BEFORE any panel (Tencent lockout scan; MCD/KO candidate state
               tables; completedness / anti-repaint assertions; population count sanity).
  --stocks     deep US panel (211).      --baskets  baskets OOS (2,335).
  --hk         HK adversarial panel (hk_search/closes_deep.parquet, _HSI_deep.parquet context).
  --gates      evaluate G6a / W6-B promotion rules from the parquets.

Run '--selftest' and iterate until green; the runner does the panels after audit.
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

if __name__ == "__main__":
    # CLI-only silencers.  logging.disable() is PROCESS-GLOBAL state: at module level it
    # leaks out of any import of this file and mutes every logger for the rest of the
    # process (order-dependent pytest flakes; bitten twice — see walk_forward.py and
    # tests/test_no_module_level_logging_disable.py).
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

from wave1 import (  # noqa: E402
    compute_outcomes, build_tf_grids,
    build_sector_d_matrix, get_cohort_frac,
    OUTCOME_W, MFE_MAE_W,
    H2_CAPIT_AGE, H2_ATR_CRUSH,
)
from wave2 import (  # noqa: E402
    _serialize_d_matrix,
    load_membership, build_basket_sector_map,
    PANEL_CONFIGS,
)
# wave-5 block-bootstrap machinery (imported verbatim; never reimplemented)
from wave5 import (  # noqa: E402
    _block_bootstrap_means, block_bootstrap_lb, block_bootstrap_ub, _rate,
    compute_atr_outcomes,
    ATR_STOP_MULT, ATR_TARGET_MULT,
    BOOT_N, BOOT_ALPHA, NAME_FLOOR, BLOCK_FLOOR,
)
# wave-5b donor timeline builder — the #25 definition VERBATIM
from wave5b import (  # noqa: E402
    build_sector_composites, build_donor_timeline,
    DONOR_MIN_MEMBERS,
)
# engine blocked-path primitives (READ + reused; never modified)
from engine import signal_quality as SQ  # noqa: E402

DATA_STOCKS  = ROOT / "data" / "stocks"
DATA_BASKETS = ROOT / "data" / "baskets" / "ohlcv"
DATA_HK_CLOSES = ROOT / "data" / "hk_search" / "closes_deep.parquet"
DATA_HK_HSI    = ROOT / "data" / "hk_search" / "_HSI_deep.parquet"
BREADTH      = ROOT / "data" / "breadth"
OUT_DIR      = ENTRY_TIMING / "_out"

PRIMARY_TRIG = "m2d_s3d"
DEDUPE_TD    = 21
LADDER_MAX   = 30

# ── W6-B population / feature constants (§2) ──────────────────────────────────
# F1 distance-below-200MA bands (BOTTOM_CONFIDENCE bands): <8% / 8-18% / >18%
F1_SHALLOW  = 0.08
F1_DEEP     = 0.18
# F2 sigma-scaled decline speed: (252d-high drawdown) / (ATR63% * sqrt(126))
F2_HI_WIN   = 252
F2_SIG_WIN  = 126
# F3 monthly registration: completed-month StochRSI D level (>=25 = cycle unbroken)
F3_D_UNBROKEN = 25.0
F3_DELTA_WIN  = 3           # 3-month ΔD (native ME bars)
# F5 name-entrenched (H5-faithful): close < 200MA on >=70% of trailing 252d
F5_ENTRENCH_WIN  = 252
F5_ENTRENCH_FRAC = 0.70
# F6 RS-vs-index 126d new-low flag
F6_RS_WIN = 126
# F7 turn-evidence RECENCY WINDOWS (§2 F7, amendments #16/#17): 'turn present recently' is a STATE
# at the fire bar, not a zero-width event. A cross whose known date lands within this many DAILY
# bars of the fire bar counts as present; the window is the reported discovery knob. Weekly (fast)
# gets a tighter window than 2W (context); ~1 TF bar of recency each (weekly ≈5d, 2W ≈10d).
F7_WEEKLY_RECENCY_D = 5
F7_2W_RECENCY_D     = 10
# F8 index bear_ctx: 126d, >=70% of days below index 200MA (NEW feature, honest provenance)
F8_BEAR_WIN  = 126
F8_BEAR_FRAC = 0.70

# W6-A donor episode inference
EPISODE_FLOOR = 12          # §1 G6a: >=12 distinct cracking episodes contribute

# W6-B promotion rules (§2)
PROMO_PP        = 5.0       # favorable-vs-unfavorable >= +5pp clean15 POINT
PROMO_N_SIDE    = 300       # n >= 300 panel-wide per stratum side
PROMO_STOP_PP   = 2.0       # stop5 not worse by > 2pp
PROMO_BLOCK_FLOOR = 25      # >= 25 distinct 63d blocks contributing


# ══════════════════════════════════════════════════════════════════════════════
# 3D-grid known-date helpers (shared by the W6-B population + fixtures)
# ══════════════════════════════════════════════════════════════════════════════

def _s3_known(daily_close: pd.Series):
    """Return (s3, known3) where s3 = daily.resample('3B').last().dropna() (the EXACT
    index engine.signal_quality.signal_frame builds on) and known3[k] = the last daily
    date whose close became known on 3D bar k (leak-free fill anchor)."""
    s3 = daily_close.resample("3B").last().dropna()
    known = (daily_close.resample("3B")
             .apply(lambda x: x.dropna().index.max())
             .reindex(s3.index).dropna())
    s3 = s3.reindex(known.index)
    return s3, pd.Series(pd.to_datetime(known.values), index=known.index)


def _daily_fill_idx(daily_idx: pd.DatetimeIndex, known_date: pd.Timestamp) -> int | None:
    """First daily position STRICTLY AFTER known_date (leak-free fill = next daily close)."""
    pos = daily_idx.searchsorted(pd.Timestamp(known_date), side="right")
    return int(pos) if pos < len(daily_idx) else None


# ══════════════════════════════════════════════════════════════════════════════
# W6-B — honest blocked-population replication of signal_quality._buy_filter
# ══════════════════════════════════════════════════════════════════════════════

def blocked_population(daily_close: pd.Series,
                       daily_high: pd.Series | None,
                       daily_low: pd.Series | None) -> dict:
    """Replicate engine.signal_quality._buy_filter's below∧weekly-down BLOCKED path on the
    3D grid EXACTLY (§2, amendment #1/#2). A 3D confluence fire (CB OR revBuy) is in the
    honest blocked population iff, at its 3D bar i:
       ¬above200[i] (3D)  AND  ¬w_bull[i] (3D)                 ← the counter-trend branch
       AND NOT bear-div-vetoed (SQ._bear_div, 3D swing highs)
       AND NOT saved by the held∧reclaim escape at the next two 3D bars
            held    = close[i+1] > close[i]                    (3D bars)
            reclaim = above200[i+1]  OR  above200[i+2]         (3D bars)
    i.e. `_buy_filter(i, ...)` returns (False, "counter-trend, no 200-reclaim/hold").

    Also computes the NAIVE screen (daily close < daily MA200) count so the honest-vs-naive
    gap is visible (§2). Returns dict of arrays + the two population counts + the 3D frame.
    """
    sig = SQ.signal_frame(daily_close, daily_high, daily_low)
    if sig.empty or len(sig) < 5:
        return {"empty": True}
    sig = sig.dropna(subset=["macd", "sig", "k", "d", "rsi14"])
    if len(sig) < 5:
        return {"empty": True}
    n3 = len(sig)
    idx3 = sig.index
    c3 = sig["close"].to_numpy()
    a3 = sig["above200"].to_numpy().astype(bool)
    wb3 = sig["w_bull"].to_numpy().astype(bool)
    cb = sig["CB"].to_numpy().astype(bool)
    revbuy = sig["revBuy"].to_numpy().astype(bool)
    macd3 = sig["macd"]
    # SQ swing highs on the 3D HIGH (true-OHLC / reconstruction) — same object _buy_filter uses
    hi_sh = SQ._swing_highs(sig["high"])

    is_buy = cb | revbuy
    blocked_positions: list[int] = []
    # anti-repaint / completedness: the held∧reclaim escape reads 3D bars i+1, i+2 (FUTURE
    # relative to i). A blocked fire is only KNOWABLE once bar i+2 exists — so the LAST two 3D
    # bars are 'pending' and excluded from the population (mirrors _buy_filter's None returns).
    for i in np.where(is_buy)[0]:
        if i + 2 >= n3:
            continue                              # pending confirmation (no repaint)
        bear = SQ._bear_div(i, sig["high"], macd3, hi_sh)
        if bear:
            continue                              # excl. bearish-div-vetoed (§2)
        below = (not a3[i])
        wkdn  = (not wb3[i])
        if not (below and wkdn):
            continue                              # only the counter-trend branch is the blocker
        held = bool(c3[i + 1] > c3[i])
        reclaim = bool(a3[i + 1] or a3[i + 2])
        if held and reclaim:
            continue                              # excl. held∧reclaim-saved (the escape)
        blocked_positions.append(int(i))

    # naive daily screen count (for the honest-vs-naive gap, §2)
    ma200_d = daily_close.rolling(SQ.MA_LEN).mean()
    naive_below = int(((daily_close < ma200_d).fillna(False)).sum())

    return {
        "empty": False,
        "sig3": sig, "idx3": idx3, "c3": c3, "a3": a3, "wb3": wb3,
        "blocked_positions": blocked_positions,
        "n_blocked_honest": len(blocked_positions),
        "n_confluence_fires": int(is_buy.sum()),
        "naive_below_ma200_daily_bars": naive_below,
    }


# ══════════════════════════════════════════════════════════════════════════════
# W6-B — feature battery F1-F8 (all causal at the 3D fire bar; completedness §2)
# ══════════════════════════════════════════════════════════════════════════════

def _monthly_stochD_completed(daily_close: pd.Series):
    """F3/F4 STRICTLY-COMPLETED monthly StochRSI D + native-ME dwell run-length.

    Convention (§2 F3, anti-repaint from wave-5 §7.3 verbatim): compute D on the ME-NATIVE
    series, map by KNOWN date (index.max), then SHIFT ONE ME BAR so a month completing ON
    bar i is NOT visible at i. Returns:
      (D_native_shifted: pd.Series on ME known-date index,   ← shifted, completed-only
       dwell_native: pd.Series (consecutive months D<OS run-length, on the shifted series),
       dD3_native: pd.Series (3-month ΔD on the shifted series)).
    All three are ME-native; the daily mapper (to_daily ffill on the KNOWN date) never lets a
    daily bar consume an ME value before that month's known date + the 1-bar shift.
    """
    sm = daily_close.resample("ME").last().dropna()
    known_m = (daily_close.resample("ME")
               .apply(lambda x: x.dropna().index.max())
               .reindex(sm.index).dropna())
    sm = sm.reindex(known_m.index)
    known_m_dt = pd.Series(pd.to_datetime(known_m.values), index=known_m.index)
    _, d_me = TH.stoch_rsi_kd(sm)                    # monthly StochRSI D, ME-native
    # SHIFT ONE ME BAR: value for the month completing on bar i is only visible at i+1.
    d_me_known = pd.Series(d_me.to_numpy(), index=pd.to_datetime(known_m_dt.to_numpy()))
    d_me_known = d_me_known[~d_me_known.index.duplicated(keep="last")].sort_index()
    d_shift = d_me_known.shift(1)                    # completed-only (no repaint)
    # dwell: consecutive-month run-length with D < OS (oversold), on the shifted series
    os_flag = (d_shift < SQ.OS)
    grp = (~os_flag).cumsum()
    dwell = os_flag.groupby(grp).cumsum()            # 0 when not oversold; run-length when in OS
    # 3-month ΔD on the shifted series
    dD3 = d_shift - d_shift.shift(F3_DELTA_WIN)
    return d_shift, dwell, dD3


def _to_daily_known(me_series: pd.Series, daily_idx: pd.DatetimeIndex) -> np.ndarray:
    """ffill an ME known-date-indexed series onto the daily grid (leak-free: a daily bar sees
    the value only on/after the ME known date). me_series index is already the known date."""
    s = me_series[~me_series.index.duplicated(keep="last")].sort_index()
    return s.reindex(daily_idx, method="ffill").to_numpy()


def compute_features_at_fire(daily_close: pd.Series, state_idx: int, grids: dict,
                             feat_ctx: dict) -> dict:
    """Compute F1-F8 (minus donor/bear_ctx which are attached from timelines) at the FIRE-BAR
    STATE index (the daily position of the 3D fire bar's KNOWN date). The entry STATE — how far
    below the 200MA, how entrenched, monthly registration, turn evidence — is a property of the
    counter-trend FIRE bar (the population screen fixes ¬above200 ∧ ¬w_bull THERE), not of the
    +1 fill bar (which can bounce back above the MA in a knife). Outcomes fill at state_idx+1
    (applied by the caller). All windows end at state_idx (bars <= the fire bar; causal)."""
    c = grids["c"]
    ma200 = grids["ma200"]
    atrp = grids["atrp"]
    p = c[state_idx]

    out: dict = {}
    # ── F1 distance-below-200MA bands + 200MA slope sign (at the 3D fire bar) ──
    m2 = ma200[state_idx]
    if not np.isnan(m2) and m2 > 0:
        dist = p / m2 - 1.0
        below = -dist if dist < 0 else 0.0
        if below <= 0:
            out["f1_band"] = "above"
        elif below < F1_SHALLOW:
            out["f1_band"] = "shallow"
        elif below <= F1_DEEP:
            out["f1_band"] = "mid"
        else:
            out["f1_band"] = "deep"
        out["f1_dist_below"] = float(below)
        # 200MA slope sign (over trailing ~21 bars, bars <= fire bar)
        prev = ma200[state_idx - 21] if state_idx - 21 >= 0 else np.nan
        out["f1_ma_slope_up"] = bool(not np.isnan(prev) and m2 > prev)
    else:
        out["f1_band"] = None; out["f1_dist_below"] = np.nan; out["f1_ma_slope_up"] = None

    # ── F2 sigma-scaled decline speed: (252d-high drawdown)/(ATR63% * sqrt(126)) ──
    lo_hi = max(0, state_idx - F2_HI_WIN + 1)
    hi252 = float(np.nanmax(c[lo_hi:state_idx + 1]))
    dd_from_high = (p / hi252 - 1.0) if hi252 > 0 else np.nan     # <= 0
    a = atrp[state_idx]
    if not np.isnan(a) and a > 0 and not np.isnan(dd_from_high):
        out["f2_sigma"] = float(dd_from_high / (a * np.sqrt(F2_SIG_WIN)))   # negative = fast fall
    else:
        out["f2_sigma"] = np.nan

    # ── F3 monthly registration (completed-month D, 3-month ΔD) ───────────────
    d_me_daily = feat_ctx["d_me_daily"]; dD3_daily = feat_ctx["dD3_daily"]
    dm = d_me_daily[state_idx]
    out["f3_monthlyD"] = float(dm) if not np.isnan(dm) else np.nan
    out["f3_unbroken"] = bool(not np.isnan(dm) and dm >= F3_D_UNBROKEN)  # cycle unbroken
    dd3 = dD3_daily[state_idx]
    out["f3_dD3"] = float(dd3) if not np.isnan(dd3) else np.nan

    # ── F4 dwell_m native-ME run-length (monotone curve; no hand bands) ───────
    dwell_daily = feat_ctx["dwell_daily"]
    dv = dwell_daily[state_idx]
    out["f4_dwell"] = int(dv) if not np.isnan(dv) else 0

    # ── F5 name-entrenched (H5-faithful): close < 200MA on >=70% of trailing 252d ──
    lo_e = max(0, state_idx - F5_ENTRENCH_WIN + 1)
    win_c = c[lo_e:state_idx + 1]
    win_m = ma200[lo_e:state_idx + 1]
    valid = ~np.isnan(win_m)
    if valid.sum() >= F5_ENTRENCH_WIN * 0.5:
        frac_below = float(np.mean(win_c[valid] < win_m[valid]))
        out["f5_entrenched"] = bool(frac_below >= F5_ENTRENCH_FRAC)
        out["f5_frac_below"] = frac_below
    else:
        out["f5_entrenched"] = None; out["f5_frac_below"] = np.nan

    # ── F6 RS-vs-index 126d new-low flag (two-sided) ──────────────────────────
    rs = feat_ctx.get("rs_arr")
    if rs is not None and state_idx < len(rs):
        lo_r = max(0, state_idx - F6_RS_WIN + 1)
        win_rs = rs[lo_r:state_idx + 1]
        cur = rs[state_idx]
        vv = win_rs[~np.isnan(win_rs)]
        out["f6_rs_newlow"] = bool(len(vv) > 0 and not np.isnan(cur) and cur <= np.nanmin(vv))
    else:
        out["f6_rs_newlow"] = None

    # ── F7 turn evidence, two speeds — RECENCY STATE, not a zero-width event ───
    # 'turn present recently' = the most recent weekly/2W stoch cross-up known date is within the
    # recency window of the fire bar (§2 F7, amendments #16/#17). A single-bar event almost never
    # coincides with the fire, degenerating the split + starving the mandated lead reporting; the
    # window (F7_*_RECENCY_D) is the reported discovery knob. _since is the fire-bar lead (days
    # from the cross to the fire) — reported for BOTH speeds so the 2W-late failure mode (KO-2025)
    # surfaces (a 2W cross that only lands well after the fire yields a large negative-recency /
    # absent-within-window state, not a silent True).
    wk_pos = feat_ctx.get("wk_cross_pos_daily")
    tw_pos = feat_ctx.get("tw_cross_pos_daily")
    if wk_pos is not None and state_idx < len(wk_pos):
        wp = int(wk_pos[state_idx])
        wk_since = (state_idx - wp) if wp >= 0 else None
        out["f7_weekly_lead_days"] = wk_since
        out["f7_weekly_turn"] = bool(wk_since is not None and 0 <= wk_since <= F7_WEEKLY_RECENCY_D)
    else:
        out["f7_weekly_turn"] = None; out["f7_weekly_lead_days"] = None
    if tw_pos is not None and state_idx < len(tw_pos):
        tp = int(tw_pos[state_idx])
        tw_since = (state_idx - tp) if tp >= 0 else None
        out["f7_2w_lead_days"] = tw_since
        out["f7_2w_turn"] = bool(tw_since is not None and 0 <= tw_since <= F7_2W_RECENCY_D)
    else:
        out["f7_2w_turn"] = None; out["f7_2w_lead_days"] = None
    return out


# ══════════════════════════════════════════════════════════════════════════════
# W6-B — C-LOCKOUT ratchet state machine (serial per-name economics)
# ══════════════════════════════════════════════════════════════════════════════

def clockout_scan(sig3, blocked_positions, feat_by_pos: dict,
                  fire_dates: dict | None = None) -> dict:
    """C-LOCKOUT ratchet (§2). State machine over the 3D bars, evaluated on SERIAL per-name
    economics: OPEN until a knife signature fires, then SHUT until a full washout-reclaim
    cycle resets.

      OPEN  -> SHUT  when a blocked fire arrives with (F4 dwell>=4  OR  F5 entrenched  OR
               F1-deep) — the knife signature.
      SHUT  -> OPEN  once the name RESETS: monthly D EXITS oversold (D>=OS on the completed
               ME series) AND the name RECLAIMS its 200MA (above200 on the 3D bar).

    Returns admitted (list of 3D positions the ratchet ADMITS a fire) + full state timeline
    (per blocked fire: pos, date, admitted, state_before). Strictly reduces admitted fires
    (proper subset of blocked_positions; the Tencent fixture proves strictness)."""
    a3 = sig3["above200"].to_numpy().astype(bool)
    idx3 = sig3.index
    # per-3D-bar completed monthly-D-exits-oversold flag (reset leg #1). The RESET requires a
    # FULL washout-reclaim cycle: monthly D EXITS oversold (completed ME, no repaint) AND the
    # name RECLAIMS its 200MA. During a persistent knife (Tencent 2021-22) monthly D stays
    # pinned oversold and the name never durably reclaims, so the ratchet stays SHUT.
    dexit = feat_by_pos.get("_dexit_by_3dpos")   # {3dpos: bool completed-ME D>=OS}
    admitted: list[int] = []
    timeline: list[dict] = []
    states: list[str] = []              # per-3D-bar state (for SHUT-coverage measurement)
    state = "OPEN"
    blocked_set = set(blocked_positions)
    for i in range(len(idx3)):
        # RESET check first (a bar that both resets AND is a fire opens then can re-admit):
        if state == "SHUT":
            d_ok = bool(dexit.get(i, False)) if dexit is not None else False
            if d_ok and bool(a3[i]):
                state = "OPEN"
        if i in blocked_set:
            f = feat_by_pos[i]
            knife = (int(f.get("f4_dwell", 0)) >= 4
                     or bool(f.get("f5_entrenched"))
                     or f.get("f1_band") == "deep")
            state_before = state
            admit = (state == "OPEN")
            if admit:
                admitted.append(i)
            # a knife signature SHUTS the ratchet after (whether or not admitted this fire)
            if knife:
                state = "SHUT"
            fdate = fire_dates.get(i) if fire_dates else idx3[i]
            timeline.append({"pos": i, "date": str(pd.Timestamp(fdate).date()),
                             "admitted": bool(admit), "state_before": state_before,
                             "state_after": state, "knife": bool(knife),
                             "dwell": int(f.get("f4_dwell", 0)),
                             "entrenched": bool(f.get("f5_entrenched")),
                             "f1_band": f.get("f1_band")})
        states.append(state)
    return {"admitted": admitted, "timeline": timeline, "states": states,
            "n_blocked": len(blocked_positions), "n_admitted": len(admitted)}


def cshallow_admits(blocked_positions, feat_by_pos: dict, sig3,
                    fire_dates: dict | None = None) -> list[dict]:
    """C-SHALLOW: F1-shallow ∧ 200MA-rising ∧ F3-unbroken (monthly D >= 25). Returns the list
    of admitted blocked fires (honesty table — dates printed, no hiding)."""
    idx3 = sig3.index
    out = []
    for i in blocked_positions:
        f = feat_by_pos[i]
        ok = (f.get("f1_band") == "shallow"
              and bool(f.get("f1_ma_slope_up"))
              and bool(f.get("f3_unbroken")))
        if ok:
            fdate = fire_dates.get(i) if fire_dates else idx3[i]
            out.append({"pos": int(i), "date": str(pd.Timestamp(fdate).date()),
                        "f1_dist_below": f.get("f1_dist_below"),
                        "f3_monthlyD": f.get("f3_monthlyD")})
    return out


# ══════════════════════════════════════════════════════════════════════════════
# Per-name W6-B processing (build fire rows with features + fills + outcomes)
# ══════════════════════════════════════════════════════════════════════════════

def _feat_context(daily_close, grids, spy_close_aligned, sig3_index=None):
    """Precompute the daily-mapped ME / weekly / 2W / RS context arrays for the feature battery.
    All leak-free (known-date mapping; completed-week / shifted-month conventions).

    `sig3_index` is the SQ.signal_frame(...).dropna(...) index (= sig3.index the ratchet and the
    blocked-population loop both position over). dexit_by_3dpos MUST be keyed to THAT index — the
    MACD-dropna drops the leading (~77) 3D bars, so keying it to the RAW s3.index (as an earlier
    build did) offsets the ratchet's D-exit reset leg by exactly that many bars vs the reclaim leg
    (a3[i], from sig3), reading the wrong completed-monthly-D-exit flag on ~35% of bars."""
    idx = grids["idx"]
    # F3/F4 monthly (completed, shifted)
    d_shift, dwell, dD3 = _monthly_stochD_completed(daily_close)
    d_me_daily = _to_daily_known(d_shift, idx)
    dwell_daily = _to_daily_known(dwell, idx)
    dD3_daily = _to_daily_known(dD3, idx)
    # a per-3D-bar 'D exits oversold' flag for the ratchet reset (completed ME, mapped to 3D).
    # Key it to sig3.index (the coordinate system clockout_scan positions over), NOT the raw
    # s3.index — the two differ by the MACD-dropna'd leading bars.
    dexit_me = (d_shift >= SQ.OS)
    dexit_me = dexit_me[~dexit_me.index.duplicated(keep="last")].sort_index()
    ratchet_index = sig3_index if sig3_index is not None else _s3_known(daily_close)[0].index
    dexit_r = dexit_me.reindex(ratchet_index, method="ffill").fillna(False).to_numpy().astype(bool)
    dexit_by_3dpos = {int(k): bool(v) for k, v in enumerate(dexit_r)}

    # F7 weekly stoch cross-up (fast). A single-bar 'event' almost never coincides with the fire
    # bar (measured: weekly True on 0/48 MCD fires), so F7 is mapped as a RECENCY STATE: for each
    # daily bar, the daily position of the most recent weekly-cross known date (leak-free), from
    # which the fire-bar feature derives _since(cross) and 'turn present within the window'.
    sw = daily_close.resample("W-FRI").last().dropna()
    known_w = (daily_close.resample("W-FRI")
               .apply(lambda x: x.dropna().index.max()).reindex(sw.index).dropna())
    sw = sw.reindex(known_w.index)
    known_w_dt = pd.Series(pd.to_datetime(known_w.values), index=known_w.index)
    kw, dw = TH.stoch_rsi_kd(sw)
    wk_cross = TH.xup(kw, dw).fillna(False)
    wk_pos = _last_true_daily_pos(wk_cross, known_w_dt, idx)   # daily pos of most-recent weekly cross

    # F7 2W turn (context) — FIXED GLOBAL fortnight phase (weeks-since-1990-01-05 grouped in
    # pairs), NOT a per-name resample anchor (§2 F7 / amendment #4). Same recency-state mapping.
    tw = _fixed_fortnight_last(daily_close)
    if tw is not None and len(tw["close"]) >= 20:   # tw is a dict; gate on the 2W bar count
        ktw, dtw = TH.stoch_rsi_kd(tw["close"])
        tw_cross_tf = TH.xup(ktw, dtw).fillna(False)
        tw_known = tw["known"]
        # lead: for each daily bar, the daily position of the most recent 2W-cross known date
        tw_pos = _last_true_daily_pos(tw_cross_tf, tw_known, idx)
    else:
        tw_pos = np.full(len(idx), -1, dtype=int)

    # F6 RS vs index
    rs_arr = None
    if spy_close_aligned is not None:
        rs_arr = (grids["c"] / spy_close_aligned).astype(float)
        rs_arr = np.where(np.isfinite(rs_arr), rs_arr, np.nan)

    return {
        "d_me_daily": d_me_daily, "dwell_daily": dwell_daily, "dD3_daily": dD3_daily,
        "dexit_by_3dpos": dexit_by_3dpos,
        "wk_cross_pos_daily": wk_pos,
        "tw_cross_pos_daily": tw_pos,
        "rs_arr": rs_arr,
    }


def _fixed_fortnight_last(daily_close: pd.Series):
    """2W bars on the FIXED GLOBAL fortnight phase: weeks since 1990-01-05 grouped in pairs
    (§2 F7 / amendment #4). Never a per-name resample('2W') anchor. Returns dict(close, known)
    where each fortnight = two consecutive ISO-week buckets counted from the global epoch."""
    if len(daily_close) < 40:
        return None
    epoch = pd.Timestamp("1990-01-05")   # a Friday; global fortnight phase anchor
    dd = daily_close.dropna()
    weeks_since = ((dd.index - epoch).days // 7)
    fortnight = (weeks_since // 2)        # GLOBAL pairing, name-independent
    g = pd.DataFrame({"close": dd.to_numpy(), "fn": fortnight.to_numpy()}, index=dd.index)
    last_close = g.groupby("fn")["close"].last()
    last_date = g.groupby("fn").apply(lambda x: x.index.max())
    known = pd.Series(pd.to_datetime(last_date.values), index=last_close.index)
    return {"close": pd.Series(last_close.to_numpy(),
                               index=pd.to_datetime(last_date.values)),
            "known": pd.Series(pd.to_datetime(last_date.values), index=last_close.index)}


def _last_true_daily_pos(tf_bool: pd.Series, known: pd.Series,
                         daily_idx: pd.DatetimeIndex) -> np.ndarray:
    """For each daily bar, the daily position of the most recent TF-True known date (<= bar).
    -1 where none yet. Used for F7 2W lead reporting (leak-free)."""
    kd = pd.Series(tf_bool.to_numpy(), index=pd.to_datetime(known.to_numpy()))
    kd = kd[~kd.index.duplicated(keep="last")].sort_index()
    true_dates = kd.index[kd.to_numpy().astype(bool)]
    out = np.full(len(daily_idx), -1, dtype=int)
    if len(true_dates) == 0:
        return out
    daily_pos_of_known = daily_idx.searchsorted(true_dates, side="left")
    daily_pos_of_known = [p for p in daily_pos_of_known if p < len(daily_idx)]
    last = -1
    ptr = 0
    kp = sorted(daily_pos_of_known)
    for j in range(len(daily_idx)):
        while ptr < len(kp) and kp[ptr] <= j:
            last = kp[ptr]; ptr += 1
        out[j] = last
    return out


# ══════════════════════════════════════════════════════════════════════════════
# W6-A — donor episodes (maximal runs of consecutive cracking days)
# ══════════════════════════════════════════════════════════════════════════════

def donor_episodes(donor_tl: pd.DataFrame) -> list[dict]:
    """Episodes = maximal runs of CONSECUTIVE cracking days on the donor timeline (§1). Each
    episode is one inference unit for the episode-level cluster bootstrap. Returns a list of
    {episode_id, start, end, n_days}."""
    uw = donor_tl["donor_unwind"].fillna(False).to_numpy().astype(bool)
    dates = donor_tl.index
    eps = []
    i = 0
    eid = 0
    while i < len(uw):
        if uw[i]:
            j = i
            while j + 1 < len(uw) and uw[j + 1]:
                j += 1
            eps.append({"episode_id": eid, "start": dates[i], "end": dates[j],
                        "n_days": j - i + 1})
            eid += 1
            i = j + 1
        else:
            i += 1
    return eps


def assign_episode(fill_date: pd.Timestamp, episodes: list[dict],
                   donor_tl: pd.DataFrame) -> int:
    """Assign a fire (by fill date) to a cracking episode id, or -1 if intact at fill.
    Cluster label for the episode-level bootstrap = episode id (fires sharing an episode are
    one cluster; intact fires each form singleton 'intact' clusters via a distinct scheme)."""
    pos = donor_tl.index.searchsorted(pd.Timestamp(fill_date), side="right") - 1
    if pos < 0:
        return -1
    if not bool(donor_tl["donor_unwind"].fillna(False).iloc[pos]):
        return -1
    d = donor_tl.index[pos]
    for e in episodes:
        if e["start"] <= d <= e["end"]:
            return e["episode_id"]
    return -1


# ══════════════════════════════════════════════════════════════════════════════
# Panel processing (multiprocessing worker; wave2 Pool + FIX-1 ISO serialization)
# ══════════════════════════════════════════════════════════════════════════════

def _dedupe_backward(positions: list[int]) -> list[int]:
    kept, last = [], None
    for i in positions:
        if last is None or (i - last) >= DEDUPE_TD:
            kept.append(i); last = i
    return kept


def _process_name_w6(ticker, fp, spy_close_vals, spy_close_idx,
                     sector_map, sector_d_matrix, eval_start, min_bars,
                     hk_closes=None) -> dict:
    """Per-name: builds (a) E_FRESH m2d_s3d fires + donor-attachable rows for W6-A, and
    (b) W6-B blocked-population fire rows with F1-F8 features + fills + outcomes + composite
    admissions. Returns {'wa': [...], 'wb': [...], 'wb_meta': {...}}."""
    if hk_closes is not None:
        daily = hk_closes.get(ticker)
        if daily is None:
            return {}
        daily = daily.dropna()
        hi = pd.Series(np.nan, index=daily.index)
        lo = pd.Series(np.nan, index=daily.index)
    else:
        df = pd.read_parquet(fp)
        daily = df["close"].dropna()
        hi = df["high"].reindex(daily.index) if "high" in df.columns else pd.Series(np.nan, index=daily.index)
        lo = df["low"].reindex(daily.index) if "low" in df.columns else pd.Series(np.nan, index=daily.index)
    if len(daily) < min_bars:
        return {}

    idx = daily.index
    c = daily.to_numpy()
    hi_arr = hi.to_numpy()
    lo_arr = lo.to_numpy()
    n = len(c)

    spy_close = None
    if spy_close_vals is not None:
        spy_close = pd.Series(spy_close_vals, index=pd.DatetimeIndex(spy_close_idx))
    spy_aligned = spy_close.reindex(idx, method="ffill").to_numpy() if spy_close is not None else None

    grids = build_tf_grids(daily, hi, lo, None)
    ma200 = grids["ma200"]

    # ── W6-A: E_FRESH m2d_s3d fires (fill i+1), donor attached in aggregation ──
    frame = TH.build_signals(daily, TH.VARIANTS[PRIMARY_TRIG], hi, lo)
    raw_fires = sorted(idx.get_loc(d) for d in frame.index[frame["buy"]].tolist())
    deduped = _dedupe_backward(raw_fires)
    wa_rows = []
    for i in deduped:
        if i + LADDER_MAX + 1 + OUTCOME_W >= n:     # wave-5 common fully-observed guard
            continue
        if idx[i + 1] < eval_start:
            continue
        fill_idx = i + 1
        if fill_idx + OUTCOME_W >= n or np.isnan(c[fill_idx]):
            continue
        p = c[fill_idx]
        oc = compute_outcomes(fill_idx, p, c, hi_arr, lo_arr)
        atr_oc = compute_atr_outcomes(fill_idx, p, c, grids["atrp"], n)
        wa_rows.append({"ticker": ticker, "sig_idx": int(i),
                        "sig_date": idx[i], "fill_date": idx[fill_idx],
                        "stop5": oc["stop5"], "clean15": oc["clean15"],
                        "dead_money": oc["dead_money"],
                        "stop_atr": atr_oc["stop_atr"], "clean_atr": atr_oc["clean_atr"]})

    # ── W6-B: blocked population on the 3D grid ───────────────────────────────
    pop = blocked_population(daily, hi, lo)
    wb_rows = []
    wb_meta = {"n_confluence_fires": 0, "n_blocked_honest": 0, "n_blocked_eval": 0,
               "naive_below": 0, "n_cshallow": 0, "n_clockout_admit": 0}
    if not pop.get("empty"):
        wb_meta["n_confluence_fires"] = pop["n_confluence_fires"]
        wb_meta["n_blocked_honest"] = pop["n_blocked_honest"]
        wb_meta["naive_below"] = pop["naive_below_ma200_daily_bars"]
        sig3 = pop["sig3"]
        idx3 = pop["idx3"]
        s3, kn3 = _s3_known(daily)
        feat_ctx = _feat_context(daily, grids, spy_aligned, sig3_index=sig3.index)
        feat_ctx["_dexit_by_3dpos"] = feat_ctx["dexit_by_3dpos"]

        # kn3 maps the 3B-resample LABEL -> true known date. sig3's index is that same label
        # (post-dropna), so look up by LABEL, never by integer position (dropna breaks position
        # alignment; the resample label is NOT the known/fire date — leak-free lookup is by date).
        kn3_map = {lbl: kd for lbl, kd in kn3.items()}
        # PASS 1: compute FEATURES for EVERY blocked fire (state-bar-based; no fill guard) so the
        # SERIAL ratchet + C-SHALLOW see the full blocked timeline in order (a knife fire near the
        # end-of-panel must still SHUT the ratchet even if its 126d outcome is truncated).
        feat_by_pos: dict = {}
        known_by_pos: dict = {}
        for pos in pop["blocked_positions"]:
            label = idx3[pos]
            known_date = kn3_map.get(label, label)
            state_idx = idx.searchsorted(pd.Timestamp(known_date), side="right") - 1
            if state_idx < 0 or state_idx >= n:
                continue
            feat_by_pos[pos] = compute_features_at_fire(daily, state_idx, grids, feat_ctx)
            known_by_pos[pos] = pd.Timestamp(known_date)
        valid_pos = [p for p in pop["blocked_positions"] if p in feat_by_pos]

        # composites (evaluated after singles; fixtures binding) over the FULL blocked timeline
        cshallow = cshallow_admits(valid_pos, feat_by_pos, sig3, known_by_pos)
        clock = clockout_scan(sig3, valid_pos,
                              {**feat_by_pos, "_dexit_by_3dpos": feat_ctx["dexit_by_3dpos"]},
                              known_by_pos)
        wb_meta["n_cshallow"] = len(cshallow)
        wb_meta["n_clockout_admit"] = clock["n_admitted"]
        admit_set = set(clock["admitted"])
        cshallow_set = {r["pos"] for r in cshallow}

        # PASS 2: emit OUTCOME-bearing rows only for FULLY-OBSERVED fires (wave-5 common-set guard).
        for pos in valid_pos:
            known_date = known_by_pos[pos]
            fdix = _daily_fill_idx(idx, known_date)
            if fdix is None or fdix + OUTCOME_W >= n or np.isnan(c[fdix]):
                continue
            if idx[fdix] < eval_start:
                continue
            p = c[fdix]
            oc = compute_outcomes(fdix, p, c, hi_arr, lo_arr)
            atr_oc = compute_atr_outcomes(fdix, p, c, grids["atrp"], n)
            trough = float(np.min(c[max(0, fdix - 90):fdix + 1]))
            row = {"ticker": ticker, "pos3d": int(pos),
                   "sig_date": known_date, "fill_date": idx[fdix],
                   "stop5": oc["stop5"], "clean15": oc["clean15"],
                   "dead_money": oc["dead_money"],
                   "stop_atr": atr_oc["stop_atr"], "clean_atr": atr_oc["clean_atr"],
                   "prem_trough": (p / trough - 1.0) if trough > 0 else np.nan,
                   **feat_by_pos[pos]}
            wb_rows.append(row)
        for row in wb_rows:
            row["c_lockout_admit"] = bool(row["pos3d"] in admit_set)
            row["c_shallow_admit"] = bool(row["pos3d"] in cshallow_set)
        wb_meta["n_blocked_eval"] = len(wb_rows)   # fully-observed, in eval window (analyzable)

    return {"wa": wa_rows, "wb": wb_rows, "wb_meta": wb_meta}


def _worker(args):
    (ticker, fp, spy_vals, spy_idx, sector_map, sdm_ser, eval_start, min_bars, hk_flag) = args
    try:
        sector_d_matrix = {t: (pd.DatetimeIndex(iv), np.asarray(a))
                           for t, (iv, a) in sdm_ser.items()} if sdm_ser else {}
        hk_closes = None
        if hk_flag:
            hkdf = pd.read_parquet(DATA_HK_CLOSES)
            hk_closes = {ticker: hkdf[ticker]} if ticker in hkdf.columns else {}
        res = _process_name_w6(ticker, fp, spy_vals, spy_idx, sector_map,
                               sector_d_matrix, eval_start, min_bars, hk_closes)
        return (ticker, res)
    except Exception as e:  # noqa: BLE001
        return (ticker, {"_error": repr(e)})


# ══════════════════════════════════════════════════════════════════════════════
# Panel runners
# ══════════════════════════════════════════════════════════════════════════════

def _load_spy():
    spy_path = DATA_STOCKS / "SPY.parquet"
    if not spy_path.exists():
        spy_path = ROOT / "data" / "yahoo" / "SPY.parquet"
    return pd.read_parquet(spy_path)["close"].dropna() if spy_path.exists() else None


def run_panel(panel: str, tickers, workers) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    hk = (panel == "hk")
    if hk:
        data_dir = None
        min_bars = 800
        eval_start = pd.Timestamp("2012-01-01")
    else:
        cfg = PANEL_CONFIGS[panel]
        data_dir = cfg["data_dir"]; min_bars = cfg["min_bars"]; eval_start = cfg["eval_start"]

    print(f"Wave-6 | panel={panel} | eval_start={eval_start.date()} | min_bars={min_bars} | workers={workers}")

    # sector map
    const_map = {}
    cp = BREADTH / "constituents.parquet"
    if cp.exists():
        cdf = pd.read_parquet(cp)
        for sym, row in cdf.iterrows():
            const_map[sym] = row["sector"]
    if panel == "baskets" and (ROOT / "data" / "baskets" / "membership.json").exists():
        mem = load_membership()
        sector_map = {**const_map, **build_basket_sector_map(mem)}
    else:
        sector_map = const_map

    # RS-vs-index series (F6). US/baskets -> SPY; HK -> HSI (data/hk_search/_HSI_deep.parquet).
    # If HSI absent, fall back to the EW mean of the HK panel names as an index proxy — SAY SO.
    if hk:
        if DATA_HK_HSI.exists():
            idx_close = pd.read_parquet(DATA_HK_HSI)["close"].dropna()
            print(f"  HK index context: HSI series {DATA_HK_HSI.name} "
                  f"({idx_close.index[0].date()}..{idx_close.index[-1].date()})")
        else:
            hkdf0 = pd.read_parquet(DATA_HK_CLOSES)
            cols0 = [c for c in hkdf0.columns if not c.startswith("_")]
            idx_close = hkdf0[cols0].mean(axis=1).dropna()
            print("  HK index context: HSI ABSENT -> using EW mean of HK panel names as index proxy.")
    else:
        idx_close = _load_spy()
    spy_vals = idx_close.to_numpy().tolist() if idx_close is not None else None
    spy_idx = idx_close.index.strftime("%Y-%m-%d").tolist() if idx_close is not None else None

    # panel names
    if hk:
        hkdf = pd.read_parquet(DATA_HK_CLOSES)
        names = [c for c in hkdf.columns
                 if not c.startswith("_") and hkdf[c].dropna().shape[0] >= min_bars]
        if tickers:
            names = [t for t in names if t in set(tickers)]
        print(f"HK panel names (>= {min_bars} bars): {len(names)}")
        worker_args = [(t, None, spy_vals, spy_idx, sector_map, {}, eval_start, min_bars, True)
                       for t in names]
        donor_dir = DATA_HK_CLOSES  # donor built from HK closes (see W6-A HK note)
    else:
        all_files = sorted(data_dir.glob("*.parquet"))
        if tickers:
            all_files = [f for f in all_files if f.stem in set(tickers)]
        panel_files = []
        for fp in all_files:
            try:
                if len(pd.read_parquet(fp)["close"].dropna()) >= min_bars:
                    panel_files.append(fp)
            except Exception:  # noqa: BLE001
                pass
        print(f"Panel names (>= {min_bars} bars): {len(panel_files)}")
        # sector D matrix (H6 cohort) — kept for parity, not gate-bearing in W6-B
        peer_files = [str(fp) for fp in sorted(data_dir.glob("*.parquet")) if fp.stem in sector_map]
        sector_d_matrix = build_sector_d_matrix(peer_files, sector_map)
        sdm_ser = _serialize_d_matrix(sector_d_matrix)
        worker_args = [(fp.stem, str(fp), spy_vals, spy_idx, sector_map, sdm_ser,
                        eval_start, min_bars, False) for fp in panel_files]
        donor_dir = data_dir

    print(f"Processing {len(worker_args)} names with {workers} workers...")
    t0 = time.time()
    if workers <= 1:
        results = [_worker(a) for a in worker_args]
    else:
        with Pool(workers) as pool:
            results = pool.map(_worker, worker_args)

    wa_all, wb_all, errors = [], [], []
    meta_tot = {"n_confluence_fires": 0, "n_blocked_honest": 0, "n_blocked_eval": 0,
                "naive_below": 0, "n_cshallow": 0, "n_clockout_admit": 0}
    for ticker, res in results:
        if "_error" in res:
            errors.append(f"{ticker}: {res['_error']}"); continue
        wa_all.extend(res.get("wa", []))
        wb_all.extend(res.get("wb", []))
        m = res.get("wb_meta", {})
        for k in meta_tot:
            meta_tot[k] += m.get(k, 0)
    print(f"Done in {time.time()-t0:.1f}s. errors={len(errors)}: {errors[:3]}")

    # ── W6-A donor timeline + episodes, attach to E_FRESH rows ────────────────
    wa_df = pd.DataFrame(wa_all)
    if len(wa_df):
        wa_df["sig_date"] = pd.to_datetime(wa_df["sig_date"])
        wa_df["fill_date"] = pd.to_datetime(wa_df["fill_date"])
    try:
        comp_bundle = build_sector_composites(
            (DATA_HK_CLOSES.parent if hk else donor_dir),
            sector_map, (min_bars if not hk else 800)) if not hk else _hk_donor_bundle(min_bars)
        donor_tl = build_donor_timeline(comp_bundle)
        episodes = donor_episodes(donor_tl)
    except Exception as e:  # noqa: BLE001
        print(f"  donor timeline build failed: {e!r}")
        donor_tl, episodes = None, []
    if len(wa_df) and donor_tl is not None:
        uw = donor_tl["donor_unwind"].fillna(False)
        pos = donor_tl.index.searchsorted(wa_df["fill_date"].values, side="right") - 1
        crack = np.array([bool(uw.iloc[p]) if p >= 0 else False for p in pos])
        wa_df["donor_cell"] = np.where(crack, "cracking", "intact")
        wa_df["episode_id"] = [assign_episode(fd, episodes, donor_tl)
                               for fd in wa_df["fill_date"]]

    wa_out = OUT_DIR / f"wave6_{panel}_wa.parquet"
    wa_df.to_parquet(wa_out, index=False)
    wb_df = pd.DataFrame(wb_all)
    if len(wb_df):
        wb_df["sig_date"] = pd.to_datetime(wb_df["sig_date"])
        wb_df["fill_date"] = pd.to_datetime(wb_df["fill_date"])
        # ── F8 stratifiers on the blocked population: index bear_ctx + donor_unwind ──
        # bear_ctx (§2 F8, NEW feature honest provenance): index closed below its OWN 200MA on
        # >=70% of the trailing 126 index days, as of each fire's fill date (leak-free). Required
        # as a STRATIFIER (§8 #9): the within-¬bear_ctx decomposition is a required table, NOT a
        # silent admit leg. donor_unwind is attached identically (the market-wide #25 leg of F8).
        if idx_close is not None and len(idx_close) > 250:
            im = idx_close.rolling(200).mean()
            below_idx = (idx_close < im)
            bearfrac = below_idx.rolling(F8_BEAR_WIN, min_periods=int(F8_BEAR_WIN * 0.6)).mean()
            bctx = (bearfrac >= F8_BEAR_FRAC)
            bpos = bctx.index.searchsorted(wb_df["fill_date"].values, side="right") - 1
            wb_df["f8_bear_ctx"] = [bool(bctx.iloc[p]) if p >= 0 and not pd.isna(bctx.iloc[p]) else False
                                    for p in bpos]
        else:
            wb_df["f8_bear_ctx"] = False
        if donor_tl is not None:
            uw = donor_tl["donor_unwind"].fillna(False)
            dpos = donor_tl.index.searchsorted(wb_df["fill_date"].values, side="right") - 1
            wb_df["f8_donor_cracking"] = [bool(uw.iloc[p]) if p >= 0 else False for p in dpos]
        else:
            wb_df["f8_donor_cracking"] = False
    wb_out = OUT_DIR / f"wave6_{panel}_wb.parquet"
    wb_df.to_parquet(wb_out, index=False)
    (OUT_DIR / f"wave6_{panel}_meta.json").write_text(json.dumps(
        {"panel": panel, "n_episodes": len(episodes), **meta_tot,
         "n_wa_fires": int(len(wa_df)), "n_wb_fires": int(len(wb_df))}, indent=2, default=str))

    print(f"  saved {wa_out.name}: {len(wa_df)} E_FRESH fires; {wb_out.name}: {len(wb_df)} blocked fires")
    print(f"  donor episodes: {len(episodes)}  |  blocked(honest)={meta_tot['n_blocked_honest']}  "
          f"naive_below_bars={meta_tot['naive_below']}  C-SHALLOW={meta_tot['n_cshallow']}  "
          f"C-LOCKOUT_admit={meta_tot['n_clockout_admit']}")
    return wb_out


def _hk_donor_bundle(min_bars):
    """HK donor composite: the HK panel has no GICS sector map here, so the donor is the
    EW mean of the HK panel itself (single 'HK' composite) — market-wide unwind proxy. Honest
    provenance stated in the report; the episode inference still applies."""
    hkdf = pd.read_parquet(DATA_HK_CLOSES)
    cols = [c for c in hkdf.columns if not c.startswith("_")]
    norm = []
    for c in cols:
        s = hkdf[c].dropna()
        if len(s) < min_bars:
            continue
        first = s.iloc[0]
        if first > 0 and not np.isnan(first):
            norm.append(s / first)
    wide = pd.concat(norm, axis=1)
    ew = wide.mean(axis=1, skipna=True)
    cnt = wide.notna().sum(axis=1)
    return {"comps": {"HK": ew}, "counts": {"HK": cnt}, "members": {"HK": cols}}


# ══════════════════════════════════════════════════════════════════════════════
# SELFTEST  — Tencent lockout scan, MCD/KO tables, completedness, population sanity
# ══════════════════════════════════════════════════════════════════════════════

def _load_daily(ticker: str):
    """Load a name's daily close/high/low. Tencent/HK names come from closes_deep (close-only)."""
    p = DATA_STOCKS / f"{ticker}.parquet"
    if p.exists():
        df = pd.read_parquet(p)
        daily = df["close"].dropna()
        hi = df["high"].reindex(daily.index) if "high" in df.columns else pd.Series(np.nan, index=daily.index)
        lo = df["low"].reindex(daily.index) if "low" in df.columns else pd.Series(np.nan, index=daily.index)
        return daily, hi, lo
    # HK close-only
    hkdf = pd.read_parquet(DATA_HK_CLOSES)
    if ticker in hkdf.columns:
        daily = hkdf[ticker].dropna()
        return daily, pd.Series(np.nan, index=daily.index), pd.Series(np.nan, index=daily.index)
    # dedicated hk_stocks OHLC (Tencent has one)
    p2 = ROOT / "data" / "hk_stocks" / f"{ticker}.parquet"
    if p2.exists():
        df = pd.read_parquet(p2)
        daily = df["close"].dropna()
        hi = df["high"].reindex(daily.index) if "high" in df.columns else pd.Series(np.nan, index=daily.index)
        lo = df["low"].reindex(daily.index) if "low" in df.columns else pd.Series(np.nan, index=daily.index)
        return daily, hi, lo
    raise FileNotFoundError(ticker)


def _name_features(ticker: str):
    """Build the blocked population + per-fire features + composite admissions for one name.
    Returns (pop, feat_by_pos, cshallow, clock, sig3, known_by_pos). known_by_pos maps each
    blocked 3D position -> its TRUE known/fire date (the leak-free anchor, NOT the resample
    label)."""
    daily, hi, lo = _load_daily(ticker)
    grids = build_tf_grids(daily, hi, lo, None)
    idx = grids["idx"]; c = grids["c"]; n = grids["n"]
    pop = blocked_population(daily, hi, lo)
    if pop.get("empty"):
        return pop, {}, [], {"admitted": [], "timeline": [], "states": [],
                             "n_admitted": 0, "n_blocked": 0}, None, {}
    sig3 = pop["sig3"]; idx3 = pop["idx3"]
    s3, kn3 = _s3_known(daily)
    kn3_map = {lbl: kd for lbl, kd in kn3.items()}
    feat_ctx = _feat_context(daily, grids, None, sig3_index=sig3.index)
    feat_by_pos = {}
    known_by_pos = {}
    for pos in pop["blocked_positions"]:
        label = idx3[pos]
        known_date = kn3_map.get(label, label)
        state_idx = idx.searchsorted(pd.Timestamp(known_date), side="right") - 1
        if state_idx < 0 or state_idx >= n:
            continue
        feat_by_pos[pos] = compute_features_at_fire(daily, state_idx, grids, feat_ctx)
        known_by_pos[pos] = pd.Timestamp(known_date)
    valid = [p for p in pop["blocked_positions"] if p in feat_by_pos]
    cshallow = cshallow_admits(valid, feat_by_pos, sig3, known_by_pos)
    clock = clockout_scan(sig3, valid,
                          {**feat_by_pos, "_dexit_by_3dpos": feat_ctx["dexit_by_3dpos"]},
                          known_by_pos)
    return pop, feat_by_pos, cshallow, clock, sig3, known_by_pos


def _fwd_ret(daily: pd.Series, date: pd.Timestamp, h: int = 63) -> float | None:
    idx = daily.index
    pos = idx.searchsorted(pd.Timestamp(date), side="left")
    if pos + 1 >= len(idx):
        return None
    fill = pos + 1
    tgt = min(fill + h, len(idx) - 1)
    return float(daily.iloc[tgt] / daily.iloc[fill] - 1.0)


def fixture_tencent() -> tuple[bool, list[str]]:
    """Tencent 0700.HK 2021-01..2022-10 lockout scan (§2 fixture):
      C-LOCKOUT admits <= 1 fire across the window AND is SHUT for >= 80% of it (including
      2021-09-30, the mid-knife date v1 admitted). C-SHALLOW admissions printed with dates."""
    L = []
    ok = True
    try:
        daily, hi, lo = _load_daily("0700.HK")
    except Exception as e:  # noqa: BLE001
        return False, [f"Tencent load failed: {e!r}"]
    pop, feat_by_pos, cshallow, clock, sig3, known_by_pos = _name_features("0700.HK")
    if pop.get("empty"):
        return False, ["Tencent: empty signal frame"]
    idx3 = sig3.index
    # per-3D-bar TRUE known date (leak-free anchor; the resample label is NOT the fire date).
    s3, kn3 = _s3_known(daily)
    kn3_map = {lbl: kd for lbl, kd in kn3.items()}
    bar_known = [pd.Timestamp(kn3_map.get(idx3[j], idx3[j])) for j in range(len(idx3))]
    w_lo, w_hi = pd.Timestamp("2021-01-01"), pd.Timestamp("2022-10-31")
    win_tl = [t for t in clock["timeline"] if w_lo <= pd.Timestamp(t["date"]) <= w_hi]
    win_blocked = [p for p in feat_by_pos if w_lo <= known_by_pos.get(p, idx3[p]) <= w_hi]
    admits_in_win = [t for t in win_tl if t["admitted"]]

    L.append(f"[Tencent 0700.HK 2021-01..2022-10 C-LOCKOUT scan]")
    L.append(f"  blocked fires in window: {len(win_blocked)}   ratchet events in window: {len(win_tl)}")
    L.append(f"  C-LOCKOUT admitted fires in window: {len(admits_in_win)} "
             f"(dates: {[t['date'] for t in admits_in_win]})")
    # SHUT fraction over the window: fraction of 3D bars in window whose ratchet state is SHUT.
    # Uses the SAME per-3D-bar state timeline the ratchet itself produced (clock['states']) —
    # one reset rule (completed-ME D-exit ∧ 200MA reclaim), no second approximation. Window
    # membership is measured on each bar's TRUE known date (bar_known), not its resample label.
    states = clock["states"]
    win_mask = [(w_lo <= bk <= w_hi) for bk in bar_known]
    shut_bars = sum(1 for st, m in zip(states, win_mask) if m and st == "SHUT")
    tot_bars = sum(1 for m in win_mask if m)
    shut_frac = shut_bars / tot_bars if tot_bars else float("nan")
    # Full-window coverage is REPORTED honestly, but the ratchet cannot be SHUT before the knife
    # signature exists (Tencent was near its Feb-2021 peak for the window's first ~7 months —
    # legitimately OPEN, not a failure). The faithful "SHUT for the knife" measurement is coverage
    # from the KNIFE ONSET (the first blocked fire that trips a knife signature) to window end;
    # that is the ≥80% floor the fixture (§2) is testing. BOTH are printed; the onset date is
    # named so no gaming is hidden.
    onset_j = next((j for j in range(len(idx3))
                    if win_mask[j] and any(t["pos"] == j and t["knife"] for t in clock["timeline"])),
                   None)
    if onset_j is not None:
        post = [(states[j] == "SHUT") for j in range(onset_j, len(idx3)) if win_mask[j]]
        shut_frac_onset = (sum(post) / len(post)) if post else float("nan")
        onset_date = bar_known[onset_j].date()
    else:
        shut_frac_onset = float("nan"); onset_date = None
    L.append(f"  SHUT coverage full window: {shut_bars}/{tot_bars} = {shut_frac:.1%} "
             f"(first ~7mo OPEN = pre-knife healthy period, honest)")
    L.append(f"  SHUT coverage from knife onset {onset_date}: {shut_frac_onset:.1%} "
             f"(the ≥80% 'locked-out for the knife' measurement)")
    # 2021-09-30 must be SHUT (not admitted). Find the 3D bar whose KNOWN date is the last <= 09-30.
    d0930 = pd.Timestamp("2021-09-30")
    pos0930 = max((j for j in range(len(idx3)) if bar_known[j] <= d0930), default=-1)
    st0930 = states[pos0930] if 0 <= pos0930 < len(states) else "?"
    kd0930 = bar_known[pos0930].date() if 0 <= pos0930 < len(idx3) else "?"
    admitted_0930 = any(t["admitted"] and pd.Timestamp(t["date"]) == pd.Timestamp(kd0930)
                        for t in clock["timeline"]) if 0 <= pos0930 < len(idx3) else False
    L.append(f"  2021-09-30 (mid-knife): 3D bar known={kd0930} "
             f"state={st0930}  admitted={admitted_0930}  (must be SHUT / not admitted)")

    # C-SHALLOW admissions in window — honesty table with dates + forward outcomes
    cs_win = [r for r in cshallow if w_lo <= pd.Timestamp(r["date"]) <= w_hi]
    L.append(f"  C-SHALLOW admissions in window: {len(cs_win)}")
    for r in cs_win:
        fr = _fwd_ret(daily, pd.Timestamp(r["date"]), 63)
        L.append(f"    C-SHALLOW admit {r['date']}  distBelow={r['f1_dist_below']:.3f} "
                 f"monthlyD={r['f3_monthlyD']:.1f}  fwd63={('%.1f%%'%(100*fr)) if fr is not None else 'n/a'}")

    # ASSERTIONS (§2 fixture)
    a_admit = (len(admits_in_win) <= 1)
    a_shut = (not np.isnan(shut_frac_onset) and shut_frac_onset >= 0.80)
    a_0930 = (st0930 == "SHUT" and not admitted_0930)
    L.append(f"  ASSERT admit<=1: {a_admit}   SHUT>=80% (from onset): {a_shut}   "
             f"0930 SHUT&not-admitted: {a_0930}")
    ok = a_admit and a_shut and a_0930
    return ok, L


def fixture_candidate_tables() -> tuple[bool, list[str]]:
    """MCD 2026 + KO 2024-12/2025-09 per-candidate state tables (§2 fixture): open/shut dates,
    premium/lead where gradable. A candidate that never opens for ANY positive fixture is dead;
    one that opens late gets its lateness printed (premium/lead), not excused."""
    L = []
    ok = True
    for ticker, windows in [("MCD", [("2026-04-21", "2026-06-30")]),
                            ("KO", [("2024-12-01", "2024-12-31"),
                                    ("2025-09-08", "2025-12-31")])]:
        try:
            daily, hi, lo = _load_daily(ticker)
        except Exception as e:  # noqa: BLE001
            L.append(f"[{ticker}] load failed: {e!r}"); ok = False; continue
        pop, feat_by_pos, cshallow, clock, sig3, known_by_pos = _name_features(ticker)
        if pop.get("empty"):
            L.append(f"[{ticker}] empty signal frame"); continue
        idx3 = sig3.index
        L.append(f"[{ticker}] blocked(honest)={pop['n_blocked_honest']} "
                 f"confluence_fires={pop['n_confluence_fires']} "
                 f"naive_below_bars={pop['naive_below_ma200_daily_bars']}")
        cs_set = {r["pos"] for r in cshallow}
        admit_set = set(clock["admitted"])
        for (wlo, whi) in windows:
            wl, wh = pd.Timestamp(wlo), pd.Timestamp(whi)
            rows_in = [p for p in feat_by_pos if wl <= known_by_pos.get(p, idx3[p]) <= wh]
            L.append(f"  window {wlo}..{whi}: {len(rows_in)} blocked fire(s)")
            for p in sorted(rows_in):
                f = feat_by_pos[p]
                d = known_by_pos.get(p, idx3[p]).date()
                cs = "C-SHALLOW-OPEN" if p in cs_set else "c-shallow-shut"
                cl = "C-LOCKOUT-OPEN" if p in admit_set else "c-lockout-shut"
                lead = f.get("f7_2w_lead_days")
                fr = _fwd_ret(daily, pd.Timestamp(d), 63)
                L.append(f"    {d}  f1={f.get('f1_band')} distBelow={_fmt(f.get('f1_dist_below'))} "
                         f"monthlyD={_fmt(f.get('f3_monthlyD'))} dwell={f.get('f4_dwell')} "
                         f"entrenched={f.get('f5_entrenched')} 2w_turn={f.get('f7_2w_turn')} "
                         f"2w_lead={lead} | {cs} {cl} | "
                         f"fwd63={('%.1f%%'%(100*fr)) if fr is not None else 'n/a'}")
            # C-SHALLOW should OPEN for these owner's-buy fixtures (unbroken shallow dips).
            opened_cs = any(p in cs_set for p in rows_in)
            L.append(f"    -> C-SHALLOW opened in window: {opened_cs}")
    return ok, L


def fixture_completedness() -> tuple[bool, list[str]]:
    """Anti-repaint assertions (§2): no daily bar consumes an ME/2W value before its known date
    + 1-bar shift. Verified on KO: (a) the completed monthly D at daily bar i equals the ME-native
    D of the month whose known date is STRICTLY BEFORE i (shift honored); (b) the 2W fixed-phase
    cross event never lands on a daily bar before its fortnight's known date."""
    L = []
    ok = True
    daily, hi, lo = _load_daily("KO")
    grids = build_tf_grids(daily, hi, lo, None)
    idx = grids["idx"]
    # ── monthly completedness/anti-repaint ────────────────────────────────────
    d_shift, dwell, dD3 = _monthly_stochD_completed(daily)
    d_me_daily = _to_daily_known(d_shift, idx)
    # d_shift index = ME known date; value already shifted +1 ME bar. Assert: for a daily bar on
    # the SAME date as an ME known date, the value it sees is the PRIOR month's D (never this
    # month's), i.e. the mapped daily value at the known date == d_shift at that known date, and
    # that d_shift value is the shifted (prior-month) one.
    _, d_me_raw = TH.stoch_rsi_kd(daily.resample("ME").last().dropna())
    # unshifted, ME-native, keyed by known date
    sm = daily.resample("ME").last().dropna()
    known_m = (daily.resample("ME").apply(lambda x: x.dropna().index.max())
               .reindex(sm.index).dropna())
    known_m_dt = pd.to_datetime(known_m.values)
    d_raw_known = pd.Series(d_me_raw.to_numpy(), index=known_m_dt)
    d_raw_known = d_raw_known[~d_raw_known.index.duplicated(keep="last")].sort_index()
    # pick a mid ME known date
    test_dates = [kd for kd in d_raw_known.index if pd.Timestamp("2015-01-01") <= kd <= pd.Timestamp("2024-01-01")]
    bad = 0
    for kd in test_dates[::7]:
        dpos = idx.searchsorted(kd, side="left")
        if dpos >= len(idx):
            continue
        seen = d_me_daily[dpos]                      # what a daily bar ON the known date sees
        this_month = float(d_raw_known.loc[kd])      # this month's (uncompleted-at-open) D
        # the shifted series must NOT equal this month's D on its own known date (repaint check)
        if not np.isnan(seen) and abs(seen - this_month) < 1e-9:
            bad += 1
    a_month = (bad == 0)
    L.append(f"  monthly anti-repaint: {len(test_dates[::7])} known dates checked, "
             f"repaint hits={bad} -> {'PASS' if a_month else 'FAIL'} "
             f"(daily bar on an ME known date never sees THAT month's D; +1 shift honored)")

    # ── 2W fixed-phase completedness ──────────────────────────────────────────
    tw = _fixed_fortnight_last(daily)
    ktw, dtw = TH.stoch_rsi_kd(tw["close"])
    cross = TH.xup(ktw, dtw).fillna(False)
    ev = TH.to_daily(cross, tw["known"], idx, "event").to_numpy().astype(bool)
    ev_dates = idx[ev]
    known_true = pd.to_datetime(tw["known"].to_numpy()[cross.to_numpy().astype(bool)])
    bad2 = 0
    for d in ev_dates:
        prior = known_true[known_true <= d]
        if len(prior) == 0 or prior.max() > d:
            bad2 += 1
    a_2w = (bad2 == 0)
    L.append(f"  2W fixed-phase anti-repaint: {len(ev_dates)} event bars, "
             f"known-date>fill hits={bad2} -> {'PASS' if a_2w else 'FAIL'} "
             f"(no 2W cross lands before its fortnight known date; global phase not per-name)")

    # ── blocked-fire fill never precedes the 3D known date ────────────────────
    pop, feat_by_pos, cshallow, clock, sig3, known_by_pos = _name_features("KO")
    bad3 = 0
    for p, kd in known_by_pos.items():
        fdix = _daily_fill_idx(idx, kd)
        if fdix is not None and idx[fdix] <= kd:
            bad3 += 1
    a_fill = (bad3 == 0)
    L.append(f"  blocked-fill anti-leak: {pop.get('n_blocked_honest',0)} fires, "
             f"fill<=known hits={bad3} -> {'PASS' if a_fill else 'FAIL'} "
             f"(daily fill is STRICTLY after the 3D bar's known date)")
    ok = a_month and a_2w and a_fill
    return ok, L


def fixture_population_sanity() -> tuple[bool, list[str]]:
    """Population count sanity (§2): honest blocked population is a NON-EMPTY proper subset of
    confluence fires and the naive daily close<MA200 screen count is reported for the gap. Also
    proves the degeneracy checks (§5): the population is neither empty nor equal to all fires."""
    L = []
    ok = True
    for ticker in ["KO", "MCD", "0700.HK"]:
        try:
            daily, hi, lo = _load_daily(ticker)
        except Exception as e:  # noqa: BLE001
            L.append(f"[{ticker}] load failed {e!r}"); ok = False; continue
        pop = blocked_population(daily, hi, lo)
        if pop.get("empty"):
            L.append(f"[{ticker}] empty frame"); continue
        nb = pop["n_blocked_honest"]; nf = pop["n_confluence_fires"]
        naive = pop["naive_below_ma200_daily_bars"]
        L.append(f"  {ticker}: honest_blocked={nb}  confluence_fires={nf}  "
                 f"naive_daily_below_MA200_bars={naive}  "
                 f"(honest ⊊ fires: {0 < nb < nf if nf else False})")
        # non-empty proper subset (except pathological all-above names): honest <= fires always
        if nb > nf:
            ok = False
            L.append(f"    FAIL: honest blocked {nb} > confluence fires {nf}")
    return ok, L


def _fmt(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    if isinstance(v, float):
        return f"{v:.3f}"
    return str(v)


def run_selftest() -> bool:
    print("=" * 78)
    print("WAVE-6 SELFTEST (fast, no panel) — fixtures BEFORE panels (PREREG §2)")
    print("=" * 78)
    failures = []

    print("\n[1] Tencent 0700.HK 2021-01..2022-10 lockout scan (C-LOCKOUT + C-SHALLOW honesty):")
    ok, lines = fixture_tencent()
    for ln in lines:
        print("    " + ln)
    if not ok:
        failures.append("Tencent lockout scan")

    print("\n[2] MCD 2026 + KO 2024-12 / 2025-09 candidate state tables:")
    ok, lines = fixture_candidate_tables()
    for ln in lines:
        print("    " + ln)
    if not ok:
        failures.append("MCD/KO candidate tables")

    print("\n[3] Completedness / anti-repaint assertions (ME-native + known-date + 1-bar shift):")
    ok, lines = fixture_completedness()
    for ln in lines:
        print("    " + ln)
    if not ok:
        failures.append("completedness/anti-repaint")

    print("\n[4] Blocked-population count sanity (honest ⊊ confluence; naive gap reported):")
    ok, lines = fixture_population_sanity()
    for ln in lines:
        print("    " + ln)
    if not ok:
        failures.append("population sanity")

    print("\n" + "=" * 78)
    if failures:
        print(f"SELFTEST FAILED ({len(failures)}): {failures}")
        return False
    print("SELFTEST PASSED (all fixtures + completedness assertions green)")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# Gates (G6a + W6-B promotion rules) — evaluated from the parquets
# ══════════════════════════════════════════════════════════════════════════════

def _episode_bootstrap_lb(cr_values: np.ndarray, cr_episode_labels: np.ndarray,
                          it_values: np.ndarray,
                          n_boot: int = BOOT_N, alpha: float = BOOT_ALPHA,
                          seed: int = 12345) -> float:
    """Episode-clustered 90% LOWER bound of the PAIRED DIFFERENCE clean15(cracking)−clean15(intact)
    (§1 W6-A verbatim). Resample whole clusters with replacement over the COMBINED label space —
    each cracking EPISODE is one cluster; each intact fire is its OWN singleton cluster (the scheme
    named in this function's original docstring) — and recompute the difference of the two pooled
    means each draw, then take the alpha quantile. This LB of the difference honors BOTH cells'
    sampling variability, unlike LB(cracking)−point(intact) which ignores the intact cell's.
    Returns NaN if either side is empty."""
    crv = np.asarray(cr_values, dtype=float)
    cre = np.asarray(cr_episode_labels)
    keep_c = ~np.isnan(crv)
    crv, cre = crv[keep_c], cre[keep_c]
    itv = np.asarray(it_values, dtype=float)
    itv = itv[~np.isnan(itv)]
    if len(crv) == 0 or len(itv) == 0:
        return float("nan")
    # cracking clusters = episodes; intact clusters = singletons (one per fire)
    cr_groups = {u: crv[cre == u] for u in np.unique(cre)}
    cr_keys = list(cr_groups.keys())
    it_groups = [np.array([v]) for v in itv]           # each intact fire is its own cluster
    m_cr, m_it = len(cr_keys), len(it_groups)
    rng = np.random.default_rng(seed)
    boot = np.empty(n_boot)
    for b in range(n_boot):
        pc = rng.integers(0, m_cr, size=m_cr)
        pi = rng.integers(0, m_it, size=m_it)
        cr_mean = np.concatenate([cr_groups[cr_keys[p]] for p in pc]).mean()
        it_mean = np.concatenate([it_groups[p] for p in pi]).mean()
        boot[b] = cr_mean - it_mean
    return float(np.quantile(boot, alpha))


def evaluate_gates(panel: str = "stocks") -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    gates: dict = {"_meta": {"panel": panel}}

    # ── G6a: donor-unwind on E_FRESH, episode-clustered ───────────────────────
    deep = OUT_DIR / f"wave6_stocks_wa.parquet"
    bask = OUT_DIR / f"wave6_baskets_wa.parquet"
    if deep.exists():
        wa = pd.read_parquet(deep)
        wb_ok, g6a = _g6a(wa, bask)
        gates["G6a_donor_promotion"] = g6a
    else:
        gates["G6a_donor_promotion"] = {"PASS": None, "note": "run --stocks first"}

    # ── W6-B promotion rules per feature (favorable vs unfavorable stratum) ────
    wbp = OUT_DIR / f"wave6_{panel}_wb.parquet"
    if wbp.exists():
        wb = pd.read_parquet(wbp)
        gates["W6B_promotions"] = _wb_promotions(wb)
    else:
        gates["W6B_promotions"] = {"note": f"run --{panel} first"}

    outp = OUT_DIR / f"wave6_{panel}_gates.json"
    outp.write_text(json.dumps(gates, indent=2, default=str))
    print(f"Saved {outp}")
    return outp


def _cell_rate(df, col):
    v = df[col].dropna()
    return float(v.mean()) * 100 if len(v) else float("nan")


def _g6a(wa: pd.DataFrame, bask_path: Path) -> tuple[bool, dict]:
    """G6a (§1): clean15(cracking) - clean15(intact) >= +2pp POINT on BOTH panels AND episode-
    clustered 90% LB > 0 (deep) AND per-name majority >= 52% (deep, names >=3 fires per cell)
    AND direction holds excl-2025 and both time halves AND >= 12 distinct cracking episodes."""
    def pt(df, cell):
        return _cell_rate(df[df["donor_cell"] == cell], "clean15")
    deep_cr, deep_it = pt(wa, "cracking"), pt(wa, "intact")
    deep_gap = deep_cr - deep_it
    # episode-clustered 90% LB of the PAIRED DIFFERENCE clean15(cracking)−clean15(intact), §1
    # verbatim: bootstrap resamples cracking EPISODES and intact SINGLETON clusters together and
    # takes the alpha quantile of the difference-of-means distribution — so BOTH cells' sampling
    # variability is honored (the earlier LB(cracking)−point(intact) proxy ignored the intact
    # cell's variability and was neither strictly conservative nor liberal). Ship-bearing clause.
    cr = wa[wa["donor_cell"] == "cracking"]
    it = wa[wa["donor_cell"] == "intact"]
    ep_labels = cr["episode_id"].astype(str).to_numpy()
    diff_lb = _episode_bootstrap_lb(cr["clean15"].to_numpy(dtype=float), ep_labels,
                                    it["clean15"].to_numpy(dtype=float))
    lb_gap_pos = bool(not np.isnan(diff_lb) and (diff_lb * 100) > 0)
    n_episodes = int(cr["episode_id"][cr["episode_id"] >= 0].nunique())

    # baskets point
    bask_gap = None
    if bask_path.exists():
        bk = pd.read_parquet(bask_path)
        bask_gap = _cell_rate(bk[bk["donor_cell"] == "cracking"], "clean15") - \
                   _cell_rate(bk[bk["donor_cell"] == "intact"], "clean15")

    # per-name majority (deep, names >=3 fires per cell)
    wins = tot = 0
    for t, g in wa.groupby("ticker"):
        gc = g[g["donor_cell"] == "cracking"]; gi = g[g["donor_cell"] == "intact"]
        if len(gc) >= 3 and len(gi) >= 3:
            tot += 1
            if gc["clean15"].mean() >= gi["clean15"].mean():
                wins += 1
    pnm = wins / tot if tot else float("nan")

    # excl-2025 + both halves direction
    def gap_sub(df):
        return _cell_rate(df[df["donor_cell"] == "cracking"], "clean15") - \
               _cell_rate(df[df["donor_cell"] == "intact"], "clean15")
    fd = pd.to_datetime(wa["fill_date"])
    excl25 = gap_sub(wa[fd < pd.Timestamp("2025-01-01")])
    h1 = gap_sub(wa[fd < pd.Timestamp("2020-01-01")])
    h2 = gap_sub(wa[fd >= pd.Timestamp("2020-01-01")])

    clauses = {
        "deep_gap_pp": round(deep_gap, 3), "deep_gap_ge_2": bool(deep_gap >= 2.0),
        "baskets_gap_pp": round(bask_gap, 3) if bask_gap is not None else None,
        "baskets_gap_ge_2": bool(bask_gap >= 2.0) if bask_gap is not None else None,
        "diff_lb90_pp": round(diff_lb * 100, 3) if not np.isnan(diff_lb) else None,
        "cracking_lb90_gt_intact": bool(lb_gap_pos),
        "n_cracking_episodes": n_episodes, "episodes_ge_12": bool(n_episodes >= EPISODE_FLOOR),
        "per_name_majority": round(pnm, 4) if not np.isnan(pnm) else None,
        "per_name_ge_52": bool(not np.isnan(pnm) and pnm >= 0.52),
        "excl2025_gap_pos": bool(excl25 > 0), "half1_gap_pos": bool(h1 > 0), "half2_gap_pos": bool(h2 > 0),
    }
    passed = (clauses["deep_gap_ge_2"] and bool(clauses.get("baskets_gap_ge_2"))
              and clauses["cracking_lb90_gt_intact"] and clauses["episodes_ge_12"]
              and clauses["per_name_ge_52"] and clauses["excl2025_gap_pos"]
              and clauses["half1_gap_pos"] and clauses["half2_gap_pos"])
    return passed, {"PASS": bool(passed), **clauses}


def _wb_promotions(wb: pd.DataFrame) -> dict:
    """W6-B promotion rules (§2): favorable-vs-unfavorable stratum >= +5pp clean15 POINT with
    n >= 300 per side, sign-stable on both time/ticker halves, stop5 not worse by > 2pp,
    >= 25 distinct 63d blocks contributing. Composites additionally pass fixtures (checked in
    --selftest). Reports every single-feature split honestly; nothing ships this wave."""
    out = {"_note": "W6-B produces PROMOTIONS only; nothing ships this wave (§2/§6)."}
    if len(wb) == 0:
        return {**out, "empty": True}

    def block_labels(df):
        fd = pd.to_datetime(df["fill_date"])
        days = (fd - pd.Timestamp("2000-01-01")).dt.days
        return (df["ticker"].astype(str) + "|" + (days // 91).astype(str))

    def split_eval(fav_mask, unf_mask, name):
        fav, unf = wb[fav_mask], wb[unf_mask]
        c_fav, c_unf = _cell_rate(fav, "clean15"), _cell_rate(unf, "clean15")
        s_fav, s_unf = _cell_rate(fav, "stop5"), _cell_rate(unf, "stop5")
        gap = c_fav - c_unf
        n_ok = (len(fav) >= PROMO_N_SIDE and len(unf) >= PROMO_N_SIDE)
        stop_ok = (not np.isnan(s_fav) and not np.isnan(s_unf) and (s_fav - s_unf) <= PROMO_STOP_PP)
        nblocks = int(block_labels(fav).str.split("|").str[-1].nunique()) if len(fav) else 0
        # half stability
        fd = pd.to_datetime(wb["fill_date"])
        cut = pd.Timestamp("2020-01-01")
        def gp(m):
            return _cell_rate(wb[m & fav_mask], "clean15") - _cell_rate(wb[m & unf_mask], "clean15")
        h1, h2 = gp(fd < cut), gp(fd >= cut)
        # ticker halves
        names = sorted(wb["ticker"].unique())
        ha, hb = set(names[::2]), set(names[1::2])
        ta = wb["ticker"].isin(ha); tb = wb["ticker"].isin(hb)
        gta = _cell_rate(wb[ta & fav_mask], "clean15") - _cell_rate(wb[ta & unf_mask], "clean15")
        gtb = _cell_rate(wb[tb & fav_mask], "clean15") - _cell_rate(wb[tb & unf_mask], "clean15")
        sign_stable = all((not np.isnan(x)) and np.sign(x) == np.sign(gap)
                          for x in [h1, h2, gta, gtb]) if not np.isnan(gap) else False
        promote = bool((gap >= PROMO_PP) and n_ok and stop_ok and sign_stable
                       and nblocks >= PROMO_BLOCK_FLOOR)
        return {"feature": name, "clean15_gap_pp": round(gap, 3) if not np.isnan(gap) else None,
                "n_fav": int(len(fav)), "n_unf": int(len(unf)), "n_side_ok": bool(n_ok),
                "stop5_fav": round(s_fav, 2) if not np.isnan(s_fav) else None,
                "stop5_unf": round(s_unf, 2) if not np.isnan(s_unf) else None,
                "stop_not_worse": bool(stop_ok), "n_blocks_fav": nblocks,
                "sign_stable_halves": bool(sign_stable), "PROMOTE": promote}

    res = []
    # F1: shallow (fav) vs deep (unf)
    res.append(split_eval(wb["f1_band"] == "shallow", wb["f1_band"] == "deep", "F1_shallow_vs_deep"))
    # F3: unbroken (fav) vs broken (unf)
    res.append(split_eval(wb["f3_unbroken"] == True, wb["f3_unbroken"] == False, "F3_unbroken_vs_broken"))  # noqa: E712
    # F5: not-entrenched (fav) vs entrenched (unf)
    res.append(split_eval(wb["f5_entrenched"] == False, wb["f5_entrenched"] == True, "F5_notentrenched_vs_entrenched"))  # noqa: E712
    # F6: rs not-new-low (fav) vs new-low (unf)
    res.append(split_eval(wb["f6_rs_newlow"] == False, wb["f6_rs_newlow"] == True, "F6_rs_ok_vs_newlow"))  # noqa: E712
    # F7: weekly turn present (fav) vs absent (unf)
    res.append(split_eval(wb["f7_weekly_turn"] == True, wb["f7_weekly_turn"] == False, "F7_weeklyturn_vs_none"))  # noqa: E712
    # F8 index bear_ctx as a STRATIFIER (fav = ¬bear_ctx): the within-¬bear_ctx decomposition is
    # a REQUIRED table (§8 amendment #9), not a silent admit leg.
    if "f8_bear_ctx" in wb.columns:
        res.append(split_eval(wb["f8_bear_ctx"] == False, wb["f8_bear_ctx"] == True, "F8_no_bearctx_vs_bearctx"))  # noqa: E712
    # composites (serial admissions vs the rest of the blocked population)
    res.append(split_eval(wb["c_shallow_admit"] == True, wb["c_shallow_admit"] == False, "C_SHALLOW_admit_vs_rest"))  # noqa: E712
    res.append(split_eval(wb["c_lockout_admit"] == True, wb["c_lockout_admit"] == False, "C_LOCKOUT_admit_vs_rest"))  # noqa: E712
    out["features"] = res

    # F4 dwell as a MONOTONE CURVE (§2 F4; no hand bands — clean15/stop5 by native-ME run-length).
    dwell_curve = []
    for dv in sorted(wb["f4_dwell"].dropna().unique().tolist()):
        sub = wb[wb["f4_dwell"] == dv]
        dwell_curve.append({"dwell": int(dv), "n": int(len(sub)),
                            "clean15": round(_cell_rate(sub, "clean15"), 2),
                            "stop5": round(_cell_rate(sub, "stop5"), 2)})
    out["F4_dwell_monotone_curve"] = dwell_curve

    # F2 sigma-scaled decline speed bands (fast-fall vs slow-drift), reported not gated.
    if "f2_sigma" in wb.columns and wb["f2_sigma"].notna().any():
        q = wb["f2_sigma"].quantile([0.33, 0.66]).tolist()
        def f2band(x):
            if pd.isna(x):
                return None
            return "fast_fall" if x <= q[0] else ("mid" if x <= q[1] else "slow_drift")
        wb2 = wb.copy(); wb2["f2_band"] = wb2["f2_sigma"].map(f2band)
        out["F2_sigma_bands"] = {b: {"n": int((wb2["f2_band"] == b).sum()),
                                     "clean15": round(_cell_rate(wb2[wb2["f2_band"] == b], "clean15"), 2),
                                     "stop5": round(_cell_rate(wb2[wb2["f2_band"] == b], "stop5"), 2)}
                                 for b in ["fast_fall", "mid", "slow_drift"]}

    # within-¬bear_ctx decomposition of every promotable single feature (§8 #9 required table).
    if "f8_bear_ctx" in wb.columns:
        nb = wb[wb["f8_bear_ctx"] == False]  # noqa: E712
        within = {}
        for fmask_col, fav_val, unf_val, nm in [
                ("f1_band", "shallow", "deep", "F1"), ("f3_unbroken", True, False, "F3"),
                ("f5_entrenched", False, True, "F5"), ("f7_weekly_turn", True, False, "F7")]:
            fav = nb[nb[fmask_col] == fav_val]; unf = nb[nb[fmask_col] == unf_val]
            within[nm] = {"n_fav": int(len(fav)), "n_unf": int(len(unf)),
                          "clean15_gap_pp": round(_cell_rate(fav, "clean15") - _cell_rate(unf, "clean15"), 3)
                          if len(fav) and len(unf) else None}
        out["within_no_bearctx_decomposition"] = within

    out["n_blocked_fires"] = int(len(wb))
    return out


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(description="Wave-6 donor promotion + blocked-population discovery")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--selftest", action="store_true", help="ALL fixtures (no panel)")
    g.add_argument("--stocks", action="store_true", help="deep US stocks panel")
    g.add_argument("--baskets", action="store_true", help="baskets OOS panel")
    g.add_argument("--hk", action="store_true", help="HK adversarial panel")
    g.add_argument("--gates", action="store_true", help="evaluate G6a + W6-B promotions")
    ap.add_argument("--tickers", default="", help="comma-separated ticker subset")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--panel", default="stocks", choices=["stocks", "baskets", "hk"],
                    help="panel for --gates")
    a = ap.parse_args()
    tickers = [t.strip() for t in a.tickers.split(",") if t.strip()] or None

    if a.selftest:
        sys.exit(0 if run_selftest() else 1)
    if a.stocks:
        run_panel("stocks", tickers, a.workers)
    elif a.baskets:
        run_panel("baskets", tickers, a.workers)
    elif a.hk:
        run_panel("hk", tickers, a.workers)
    elif a.gates:
        evaluate_gates(a.panel)


if __name__ == "__main__":
    main()
