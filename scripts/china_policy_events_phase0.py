#!/usr/bin/env python3
"""Phase-0 pre-registered China policy-event study.

Pre-registration: research/CHINA_POLICY_EVENTS_PREREG.md (committed before any
outcome computation — the git timestamp is the proof).

IMPORTANT — DATE SEMANTICS (documented here per prereg mandate, cached to
data/experiments/rrr_date_semantics_check.json):

The RRR parquet index is REPORT_DATE from Eastmoney RPT_ECONOMY_DEPOSIT_RESERVE.
Cross-referencing known PBoC announcements against the A-share trading calendar
confirms REPORT_DATE = ANNOUNCE DATE (not effective date):
  - 2008-10-08: PBoC announced; effective 2008-10-15
  - 2020-01-01: New Year's Day non-trading day; PBoC announced same day
  - 2018-10-07: Sunday non-trading day; consistent with announcement semantics
  - 2012-02-18, 2015-04-19, 2018-06-24: weekends
Bias direction: announcement precedes effective date by ~1–10 business days.
Measuring from the first close AFTER the announcement captures the market's
immediate reaction to the policy signal — the economically correct anchor.

GATED TRIALS (6):
  1. F-A RRR ease  -> SHCOMP absolute log CAR
  2. F-A RRR ease  -> banks (801780) relative log CAR
  3. F-A RRR ease  -> real estate (801180) relative log CAR
  4. F-B LPR cut   -> SHCOMP absolute log CAR
  5. F-B LPR cut   -> banks (801780) relative log CAR
  6. F-B LPR cut   -> real estate (801180) relative log CAR

Exploratory (logged in ledger, NEVER enter FDR family):
  F-X RRR hike -> SHCOMP (labeled EXPLORATORY)
  F-A/F-B -> 510300 variant (descriptive repeat, no verdict)
  F-C MPC communiques -> BLOCKED-DATA (communiques.parquet absent)

Gates at H=20:
  K >= 8, NW HAC |t| >= 2.0, BH-FDR alpha=0.10 across 6 gated p-values,
  DSR >= 0.90, chronological split-half same sign.

Verdicts: GO / ACCRUE / NO-GO / KILL / BLOCKED-DATA
"""
from __future__ import annotations

import json
import pathlib

import numpy as np
import pandas as pd

from engine.validation import (
    benjamini_hochberg,
    deflated_sharpe,
    newey_west_tstat,
    ret_moments,
)
from engine.trial_ledger import TrialLedger

# ── Trial ledger declared BEFORE any computation (prereg law) ─────────────────
FAMILY = "china_policy_events"
N_TRIALS_DECLARED = 12  # 6 gated + headroom for exploratory legs
_LED = TrialLedger.with_declared_budget(N_TRIALS_DECLARED, FAMILY)

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT = pathlib.Path(".")
DATA = ROOT / "data"

RRR_PATH = DATA / "china_macro" / "rrr.parquet"
LPR_PATH = DATA / "china_macro" / "lpr_rate.parquet"
SHCOMP_PATH = DATA / "china" / "000001.SS.parquet"
ETF300_PATH = DATA / "china" / "510300.SS.parquet"
BANKS_PATH = DATA / "china_sectors" / "801780.parquet"
RESTATE_PATH = DATA / "china_sectors" / "801180.parquet"
REGIME_PATH = DATA / "china_regime" / "regime_history.parquet"
SC_PATH = DATA / "china_sector_cycles" / "backfill.parquet"
DATE_SEMANTICS_PATH = DATA / "experiments" / "rrr_date_semantics_check.json"
RESULTS_PATH = DATA / "experiments" / "china_policy_events_results.json"
REGISTRY_PATH = DATA / "experiments" / "registry_seed.json"

HORIZONS = [5, 10, 20, 40, 60]
PRIMARY_H = 20
SUSP_MAX = 5   # sessions: exclude episode if no valid price within SUSP_MAX bars
MIN_OVERLAP = 3  # minimum common bars inside a CAR window
DSR_PASS = 0.90
T_PASS = 2.0
BH_ALPHA = 0.10
MIN_K = 8


# ─────────────────────────────────────────────────────────────────────────────
# Data loading
# ─────────────────────────────────────────────────────────────────────────────

def _load_close(path: pathlib.Path, col_hint: str = "close") -> pd.Series:
    """Load a single close series, normalise index to date."""
    df = pd.read_parquet(path)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(0)
    if col_hint in df.columns:
        s = df[col_hint]
    else:
        s = df.iloc[:, 0]
    s.index = pd.to_datetime(s.index).normalize()
    return s.dropna().sort_index()


def load_events() -> dict[str, pd.DatetimeIndex]:
    """Return episode dates (same-date merge applied) for each family."""
    rrr = pd.read_parquet(RRR_PATH)
    rrr.index = pd.to_datetime(rrr.index).normalize()

    lpr = pd.read_parquet(LPR_PATH)
    lpr.index = pd.to_datetime(lpr.index).normalize()
    # Deduplicate to one row per date (same-date same-family merge)
    lpr = lpr[~lpr.index.duplicated(keep="first")].sort_index()

    fa_dates = rrr[rrr["rrr_change"] < 0].index.sort_values()
    fx_dates = rrr[rrr["rrr_change"] > 0].index.sort_values()

    # LPR cuts: any date where 1y diff < 0 OR 5y diff < 0
    d1y = lpr["lpr_1y"].diff()
    d5y = lpr["lpr_5y"].diff()
    fb_mask = (d1y < 0) | (d5y < 0)
    fb_dates = lpr[fb_mask].index.sort_values()

    return {
        "FA": fa_dates,   # RRR ease
        "FB": fb_dates,   # LPR cut
        "FX": fx_dates,   # RRR hike (exploratory)
    }


def load_market_data() -> dict:
    """Load all price series + regime / sector-cycle conditioning tables."""
    shcomp = _load_close(SHCOMP_PATH)
    etf300 = _load_close(ETF300_PATH) if ETF300_PATH.exists() else None
    banks = _load_close(BANKS_PATH)
    restate = _load_close(RESTATE_PATH)

    regime = pd.read_parquet(REGIME_PATH)
    regime.index = pd.to_datetime(regime.index).normalize()

    sc = pd.read_parquet(SC_PATH)
    sc["date"] = pd.to_datetime(sc["date"]).dt.normalize()

    # Trading calendar = SHCOMP index
    cal = shcomp.index

    return {
        "shcomp": shcomp,
        "etf300": etf300,
        "banks": banks,
        "restate": restate,
        "regime": regime,
        "sc": sc,
        "cal": cal,
    }


# ─────────────────────────────────────────────────────────────────────────────
# CAR computation
# ─────────────────────────────────────────────────────────────────────────────

def next_trading_day(d: pd.Timestamp, cal: pd.DatetimeIndex) -> pd.Timestamp | None:
    """Return first close STRICTLY AFTER d (PIT entry convention)."""
    pos = cal.searchsorted(d, side="right")
    if pos >= len(cal):
        return None
    return cal[pos]


def car_for_event(
    event_date: pd.Timestamp,
    price_series: pd.Series,
    horizon: int,
    cal: pd.DatetimeIndex,
) -> float | None:
    """Absolute log CAR for a single event at a given horizon.

    Entry: first close strictly after event_date (PIT convention).
    Suspension rule: if no valid print within SUSP_MAX sessions after the
    intended entry, episode is dropped (returns None).
    No forward-fill through gaps — gaps reduce the effective overlap count.
    """
    # Intended entry position
    entry_pos = cal.searchsorted(event_date, side="right")
    if entry_pos >= len(cal):
        return None

    # Find first valid price within SUSP_MAX sessions
    actual_pos = None
    for k in range(SUSP_MAX + 1):
        if entry_pos + k >= len(cal):
            break
        day = cal[entry_pos + k]
        if day in price_series.index and np.isfinite(price_series.get(day, np.nan)):
            actual_pos = entry_pos + k
            break
    if actual_pos is None:
        return None

    end_pos = actual_pos + horizon
    if end_pos >= len(cal):
        return None  # window runs past panel end

    window = cal[actual_pos: end_pos + 1]
    sub = price_series.reindex(window).dropna()
    if len(sub) < max(MIN_OVERLAP, horizon // 2):
        return None  # too many gaps inside window

    # Absolute log CAR
    car = float(np.log(sub.iloc[-1] / sub.iloc[0]))
    return car


def sector_relative_car(
    event_date: pd.Timestamp,
    sector_series: pd.Series,
    shcomp: pd.Series,
    horizon: int,
    cal: pd.DatetimeIndex,
) -> float | None:
    """Sector log CAR minus SHCOMP log CAR (relative measure per prereg)."""
    sec_car = car_for_event(event_date, sector_series, horizon, cal)
    if sec_car is None:
        return None
    mkt_car = car_for_event(event_date, shcomp, horizon, cal)
    if mkt_car is None:
        return None
    return sec_car - mkt_car


# ─────────────────────────────────────────────────────────────────────────────
# Episode aggregation and statistics
# ─────────────────────────────────────────────────────────────────────────────

def compute_car_series(
    event_dates: pd.DatetimeIndex,
    price_series: pd.Series,
    shcomp: pd.Series | None,
    horizon: int,
    cal: pd.DatetimeIndex,
    mode: str = "absolute",  # "absolute" or "relative"
) -> tuple[pd.Series, int]:
    """Compute episode-level CAR series.

    Same-date events have already been merged to one date by the caller.
    Returns (episode_cars, n_dropped) where n_dropped = events with no usable window.
    """
    cars = {}
    n_dropped = 0
    for d in event_dates:
        if mode == "absolute":
            c = car_for_event(d, price_series, horizon, cal)
        else:
            c = sector_relative_car(d, price_series, shcomp, horizon, cal)
        if c is None:
            n_dropped += 1
        else:
            cars[d] = c
    return pd.Series(cars, dtype=float).sort_index(), n_dropped


def run_statistics(cars: pd.Series) -> dict:
    """Run the full gate suite on an episode-level CAR series."""
    x = cars.dropna().to_numpy(float)
    K = len(x)
    result: dict = {
        "K": K,
        "mean_car": round(float(np.mean(x)), 6) if K else None,
        "median_car": round(float(np.median(x)), 6) if K else None,
        "std_car": round(float(np.std(x, ddof=1)), 6) if K > 1 else None,
    }

    if K < MIN_K:
        result["gate_k"] = "BLOCKED-POWER"
        result["hac"] = None
        result["dsr"] = None
        result["split_half"] = None
        return result

    result["gate_k"] = "PASS"

    # HAC t-stat
    nw = newey_west_tstat(x, lags=4)
    result["hac"] = nw

    # DSR
    mom = ret_moments(pd.Series(x))
    dsr_result = None
    if mom is not None and K >= 3:
        sr, sk, ku, _ = mom
        try:
            dsr_result = deflated_sharpe(
                sr, sk, ku, T=K,
                ledger=_LED, family=FAMILY,
            )
        except Exception:
            dsr_result = None
    result["dsr"] = dsr_result

    # Chronological split-half
    if K >= 4:
        h1 = x[: K // 2]
        h2 = x[K // 2:]
        m1, m2 = float(np.mean(h1)), float(np.mean(h2))
        result["split_half"] = {
            "h1_mean": round(m1, 6),
            "h2_mean": round(m2, 6),
            "same_sign": bool(
                np.sign(m1) == np.sign(m2) and m1 != 0.0 and m2 != 0.0
            ),
            "h1_K": len(h1),
            "h2_K": len(h2),
        }
    else:
        result["split_half"] = None

    return result


def compute_full_trial(
    event_dates: pd.DatetimeIndex,
    price_series: pd.Series,
    shcomp: pd.Series | None,
    cal: pd.DatetimeIndex,
    mode: str = "absolute",
    label: str = "",
    gated: bool = True,
) -> dict:
    """Compute CAR series across all horizons + statistics at PRIMARY_H."""
    all_h: dict = {}
    primary_stats: dict = {}
    primary_cars_series: list = []

    for h in HORIZONS:
        cars, n_dropped = compute_car_series(
            event_dates, price_series, shcomp, h, cal, mode
        )
        stats = run_statistics(cars)
        entry = {
            "h": h,
            "n_events": len(event_dates),
            "n_usable": len(cars),
            "n_dropped": n_dropped,
            **{k: v for k, v in stats.items() if k != "hac"},
            "hac_t": (stats.get("hac") or {}).get("t"),
            "hac_p": (stats.get("hac") or {}).get("p"),
            "hac_mean": (stats.get("hac") or {}).get("mean"),
        }
        all_h[f"h{h}"] = entry
        if h == PRIMARY_H:
            primary_stats = stats
            primary_cars_series = cars.tolist()

    return {
        "label": label,
        "gated": gated,
        "mode": mode,
        "n_events_total": len(event_dates),
        "horizons": all_h,
        "primary_h": PRIMARY_H,
        "primary_stats": primary_stats,
        "primary_cars": primary_cars_series,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Conditioning tables (descriptive only, no t-stats per prereg)
# ─────────────────────────────────────────────────────────────────────────────

def _conditioning_cell(cars: pd.Series) -> dict:
    n = int(len(cars.dropna()))
    if n < 5:
        return {"n": n}
    return {
        "n": n,
        "mean_car_h20": round(float(cars.dropna().mean()), 6),
        "median_car_h20": round(float(cars.dropna().median()), 6),
    }


def compute_conditioning_tables(
    event_dates: pd.DatetimeIndex,
    primary_cars: pd.Series,
    regime: pd.DataFrame,
    sc: pd.DataFrame,
    sector_id: str | None = None,
) -> dict:
    """Build regime and sector-cycle conditioning tables (DESCRIPTIVE ONLY)."""
    results: dict = {}

    # Join regime at event date (last known as-of event date)
    for col in ["quad", "liquidity", "cycle"]:
        if col not in regime.columns:
            continue
        tbl: dict = {}
        for ev_date in event_dates:
            if ev_date not in primary_cars.index:
                continue
            car = primary_cars.loc[ev_date]
            # Last regime label on or before event date
            sub = regime[col]
            sub = sub[sub.index <= ev_date]
            if sub.empty:
                label = "unknown"
            else:
                label = str(sub.iloc[-1])
            if label not in tbl:
                tbl[label] = []
            tbl[label].append(car)
        results[col] = {k: _conditioning_cell(pd.Series(v)) for k, v in tbl.items()}

    # Sector cycle phase (2010->)
    if sector_id is not None:
        sc_sub = sc[sc["id"] == sector_id][["date", "phase"]].copy()
        sc_sub = sc_sub.sort_values("date").set_index("date")
        phase_tbl: dict = {}
        for ev_date in event_dates:
            if ev_date not in primary_cars.index:
                continue
            car = primary_cars.loc[ev_date]
            sub_p = sc_sub[sc_sub.index <= ev_date]
            if sub_p.empty:
                phase = "n/a (pre-2010)"
            else:
                phase = str(sub_p["phase"].iloc[-1])
            if phase not in phase_tbl:
                phase_tbl[phase] = []
            phase_tbl[phase].append(car)
        results["sector_phase"] = {
            k: _conditioning_cell(pd.Series(v)) for k, v in phase_tbl.items()
        }

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Verdict logic
# ─────────────────────────────────────────────────────────────────────────────

def determine_verdict(
    stats: dict,
    bh_result: dict | None,
    trial_key: str,
    hypothesized_sign: float = 1.0,
) -> str:
    """Apply the full gate cascade and return a single verdict string."""
    K = stats.get("K", 0)
    if K < MIN_K:
        return "BLOCKED-POWER"

    mean_car = stats.get("mean_car") or 0.0
    hac = stats.get("hac") or {}
    t = hac.get("t")
    p = hac.get("p")
    dsr_dict = stats.get("dsr") or {}
    dsr_prob = dsr_dict.get("dsr") if isinstance(dsr_dict, dict) else None
    sh = stats.get("split_half") or {}
    same_sign = sh.get("same_sign", False)

    # Wrong sign
    if mean_car * hypothesized_sign < 0:
        if t is not None and abs(t) >= T_PASS:
            return "KILL"
        return "NO-GO"

    # Right sign — check all gates
    t_pass = t is not None and abs(t) >= T_PASS and mean_car * hypothesized_sign > 0
    bh_pass = False
    if bh_result and trial_key in bh_result:
        bh_pass = bool(bh_result[trial_key].get("reject", False))

    dsr_pass_flag = dsr_prob is not None and dsr_prob >= DSR_PASS
    sh_pass = same_sign

    if t_pass and bh_pass and dsr_pass_flag and sh_pass:
        return "GO"

    # Right sign but sub-threshold
    return "ACCRUE"


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> dict:
    print("=== China Policy Events Phase-0 ===")
    print(f"Date semantics: REPORT_DATE = ANNOUNCE DATE (see {DATE_SEMANTICS_PATH})")

    events = load_events()
    md = load_market_data()
    shcomp = md["shcomp"]
    cal = md["cal"]
    regime = md["regime"]
    sc = md["sc"]

    fa = events["FA"]  # 26 RRR eases
    fb = events["FB"]  # 15 LPR cuts
    fx = events["FX"]  # 27 RRR hikes (exploratory)

    print(f"F-A RRR eases: {len(fa)} episodes")
    print(f"F-B LPR cuts: {len(fb)} episodes")
    print(f"F-X RRR hikes (exploratory): {len(fx)} episodes")

    # Log exploratory trials to ledger (consumes budget headroom)
    _LED.log_trial({"trial": "FX_rrr_hike_shcomp_h20", "kind": "exploratory"},
                   family=FAMILY, note="EXPLORATORY — not in FDR family")
    _LED.log_trial({"trial": "FA_etf300_h20", "kind": "descriptive_repeat"},
                   family=FAMILY, note="descriptive 510300 repeat")
    _LED.log_trial({"trial": "FB_etf300_h20", "kind": "descriptive_repeat"},
                   family=FAMILY, note="descriptive 510300 repeat")
    _LED.log_trial({"trial": "FC_communiques", "kind": "blocked_data"},
                   family=FAMILY, note="BLOCKED-DATA: communiques.parquet absent")

    results: dict = {
        "prereg": "research/CHINA_POLICY_EVENTS_PREREG.md",
        "date_semantics": "REPORT_DATE=announce_date (verified, see rrr_date_semantics_check.json)",
        "event_counts": {
            "FA_rrr_ease": int(len(fa)),
            "FB_lpr_cut": int(len(fb)),
            "FX_rrr_hike_exploratory": int(len(fx)),
            "FC_mpc_communiques": "BLOCKED-DATA",
        },
        "primary_horizon": PRIMARY_H,
        "gated_trials": {},
        "exploratory_trials": {},
        "bh_fdr": {},
        "conditioning_tables": {},
        "verdicts": {},
        "fc_status": "BLOCKED-DATA: communiques.parquet absent on main at study start",
    }

    # ── Gated trial 1: F-A -> SHCOMP absolute ────────────────────────────────
    t1 = compute_full_trial(fa, shcomp, None, cal, "absolute", "FA->SHCOMP", gated=True)
    results["gated_trials"]["T1_FA_SHCOMP"] = t1

    # ── Gated trial 2: F-A -> banks relative ─────────────────────────────────
    t2 = compute_full_trial(fa, md["banks"], shcomp, cal, "relative", "FA->banks_rel", gated=True)
    results["gated_trials"]["T2_FA_banks_rel"] = t2

    # ── Gated trial 3: F-A -> real estate relative ────────────────────────────
    t3 = compute_full_trial(fa, md["restate"], shcomp, cal, "relative", "FA->restate_rel", gated=True)
    results["gated_trials"]["T3_FA_restate_rel"] = t3

    # ── Gated trial 4: F-B -> SHCOMP absolute ────────────────────────────────
    t4 = compute_full_trial(fb, shcomp, None, cal, "absolute", "FB->SHCOMP", gated=True)
    results["gated_trials"]["T4_FB_SHCOMP"] = t4

    # ── Gated trial 5: F-B -> banks relative ─────────────────────────────────
    t5 = compute_full_trial(fb, md["banks"], shcomp, cal, "relative", "FB->banks_rel", gated=True)
    results["gated_trials"]["T5_FB_banks_rel"] = t5

    # ── Gated trial 6: F-B -> real estate relative ────────────────────────────
    t6 = compute_full_trial(fb, md["restate"], shcomp, cal, "relative", "FB->restate_rel", gated=True)
    results["gated_trials"]["T6_FB_restate_rel"] = t6

    # ── BH-FDR across the 6 gated H=20 p-values ──────────────────────────────
    gated_pvals: dict[str, float] = {}
    gated_keys = {
        "T1_FA_SHCOMP": (t1, 1.0),
        "T2_FA_banks_rel": (t2, 1.0),
        "T3_FA_restate_rel": (t3, 1.0),
        "T4_FB_SHCOMP": (t4, 1.0),
        "T5_FB_banks_rel": (t5, 1.0),
        "T6_FB_restate_rel": (t6, 1.0),
    }
    for key, (trial, _) in gated_keys.items():
        p = (trial["primary_stats"].get("hac") or {}).get("p")
        mean = trial["primary_stats"].get("mean_car") or 0.0
        if p is not None:
            # One-sided p-value in the hypothesized positive direction
            p1 = p / 2.0 if mean > 0 else (1.0 - p / 2.0)
            gated_pvals[key] = p1

    bh_result = benjamini_hochberg(gated_pvals, alpha=BH_ALPHA) if gated_pvals else {}
    results["bh_fdr"] = bh_result

    # ── Verdicts ──────────────────────────────────────────────────────────────
    for key, (trial, sign) in gated_keys.items():
        v = determine_verdict(
            trial["primary_stats"], bh_result, key, hypothesized_sign=sign
        )
        results["verdicts"][key] = v
        trial["verdict"] = v

    # ── Exploratory: F-X RRR hikes ───────────────────────────────────────────
    tx = compute_full_trial(fx, shcomp, None, cal, "absolute", "FX->SHCOMP_exploratory", gated=False)
    tx["verdict"] = "EXPLORATORY"
    results["exploratory_trials"]["TX_FX_SHCOMP"] = tx

    # ── Descriptive repeat: 510300 ETF ────────────────────────────────────────
    if md["etf300"] is not None:
        etf300 = md["etf300"]
        # F-A only where ETF has coverage (2012->)
        fa_etf = fa[fa >= pd.Timestamp("2012-05-04")]
        td_fa = compute_full_trial(fa_etf, etf300, None, cal, "absolute",
                                   "FA->ETF300_descriptive", gated=False)
        td_fa["verdict"] = "DESCRIPTIVE"
        results["exploratory_trials"]["TD_FA_ETF300"] = td_fa

        fb_etf = fb[fb >= pd.Timestamp("2012-05-04")]
        td_fb = compute_full_trial(fb_etf, etf300, None, cal, "absolute",
                                   "FB->ETF300_descriptive", gated=False)
        td_fb["verdict"] = "DESCRIPTIVE"
        results["exploratory_trials"]["TD_FB_ETF300"] = td_fb

    # ── F-C blocked data ─────────────────────────────────────────────────────
    results["exploratory_trials"]["FC_communiques"] = {
        "verdict": "BLOCKED-DATA",
        "reason": "data/china_official/communiques.parquet not present on main at study start",
    }

    # ── Conditioning tables (descriptive only, no t-stats) ────────────────────
    # Compute primary-H CAR series for conditioning lookups
    def _primary_cars_series(event_dates, price_series, shcomp_s, mode):
        cars, _ = compute_car_series(event_dates, price_series, shcomp_s, PRIMARY_H, cal, mode)
        return cars

    fa_shcomp_cars = _primary_cars_series(fa, shcomp, None, "absolute")
    fa_banks_cars = _primary_cars_series(fa, md["banks"], shcomp, "relative")
    fa_restate_cars = _primary_cars_series(fa, md["restate"], shcomp, "relative")
    fb_shcomp_cars = _primary_cars_series(fb, shcomp, None, "absolute")
    fb_banks_cars = _primary_cars_series(fb, md["banks"], shcomp, "relative")
    fb_restate_cars = _primary_cars_series(fb, md["restate"], shcomp, "relative")

    results["conditioning_tables"] = {
        "FA_SHCOMP": compute_conditioning_tables(fa, fa_shcomp_cars, regime, sc, None),
        "FA_banks_rel": compute_conditioning_tables(fa, fa_banks_cars, regime, sc, "801780"),
        "FA_restate_rel": compute_conditioning_tables(fa, fa_restate_cars, regime, sc, "801180"),
        "FB_SHCOMP": compute_conditioning_tables(fb, fb_shcomp_cars, regime, sc, None),
        "FB_banks_rel": compute_conditioning_tables(fb, fb_banks_cars, regime, sc, "801780"),
        "FB_restate_rel": compute_conditioning_tables(fb, fb_restate_cars, regime, sc, "801180"),
    }

    # Print summary
    print("\n=== VERDICTS ===")
    for key, verdict in results["verdicts"].items():
        trial = results["gated_trials"][key]
        ps = trial["primary_stats"]
        hac = ps.get("hac") or {}
        print(
            f"  {key}: K={ps.get('K')} mean={ps.get('mean_car')} "
            f"HAC_t={hac.get('t')} verdict={verdict}"
        )
    print(f"\n  F-X hike: K={tx['primary_stats'].get('K')} "
          f"mean={tx['primary_stats'].get('mean_car')} EXPLORATORY")

    # Write results JSON
    RESULTS_PATH.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nWrote {RESULTS_PATH}")

    return results


if __name__ == "__main__":
    main()
