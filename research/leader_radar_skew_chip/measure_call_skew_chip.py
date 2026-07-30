#!/usr/bin/env python3
"""Measurement battery: call_skew_rich chip construction reassessment (2026-07-29).

Context: engine/leader_lifecycle.py fires chips["call_skew_rich"] = rr_25d >=
rr_80th_pctile, where scripts/build_leader_radar.py:_load_options_skew computes
rr_80th_pctile = daily.quantile(0.80) over the name's OWN accrued history
INCLUDING today's observation (self-inclusive), gated on >= 21 observations.
PR #3977's adversarial review measured 62 TRUE / 350 evaluated (~17.7%) on the
weekend-padded store and flagged the construction as carrying ~no information
beyond the mechanical base rate (P ~ 0.2 by exchangeability). The chip is
chip 6 of the 7-chip CROWDED k-of-n state gate (K=3), and ~343 names cross the
21-real-session gate ~2026-07-30 (post-#3977 session-true counting).

This script measures, on the real store (data/options_skew/snapshots.parquet):
  0. Replication of the review's 62/350 (padded history, production construction).
  1. Mechanical null firing rates at n=21 (iid simulation): self-inclusive vs
     leave-one-out vs persistence k-of-m variants.
  2. Dynamics battery on session-true data with expanding history (measurement-
     lane relaxation min_obs=10, labeled): per-day breadth, pooled persistence
     P(fire_t | fire_{t-1}), TRUE-run lengths - for SELF / LOO / PERSIST(3of5).
  3. Within-name permutation null (200 reps) for the same battery: does the
     observed chip inherit real temporal structure, or is it a daily coin flip?
  4. rr series structure: per-name lag-1 autocorrelation; market-factor share
     of variance (day fixed effects) -> correlated-firing risk at scale.
  5. Q80 threshold instability at young n: |Q80(first 10) - Q80(all)| in units
     of the name's rr IQR; decision instability of the last session.
  6. Day-1 activation forecast (n=21 cohort, tomorrow): share of names whose
     latest rr already clears the would-be threshold; persistence-variant
     eligibility timeline; mapping onto the radar's k_true==2 boundary cohort.

Run:  python3 research/leader_radar_skew_chip/measure_call_skew_chip.py
Deterministic (seeded). No network. Writes results JSON next to itself.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lib.nyse_calendar import is_session  # noqa: E402

STORE = ROOT / "data" / "options_skew" / "snapshots.parquet"
RADAR = ROOT / "site" / "leaderradar" / "radar.json"
OUT = Path(__file__).resolve().parent / "measurement_results.json"

MIN_OBS_PROD = 21          # production activation gate (LRV-R1c, frozen)
MIN_OBS_MEASURE = 10       # measurement-lane relaxation (labeled; NOT production)
PERSIST_K = 3              # persistence variant: >= K of last M sessions rich
PERSIST_M = 5
N_PERM = 200               # permutation-null replicates
N_SIM = 200_000            # iid-null simulation draws
SEED = 20260729

rng = np.random.default_rng(SEED)
R: dict = {"seed": SEED, "params": {
    "min_obs_prod": MIN_OBS_PROD, "min_obs_measure": MIN_OBS_MEASURE,
    "persist_k": PERSIST_K, "persist_m": PERSIST_M,
    "n_perm": N_PERM, "n_sim": N_SIM,
}}


def q80(x: np.ndarray | pd.Series) -> float:
    """Match production exactly: pandas Series.quantile(0.80), linear interp."""
    return float(pd.Series(np.asarray(x, dtype=float)).quantile(0.80))


# ── Load store ────────────────────────────────────────────────────────────────
df = pd.read_parquet(STORE)
date_col = "date" if "date" in df.columns else "asof"
df = df.copy()
df["rr"] = df["atm_call_iv"] - df["otm_put_iv"]
df["_d"] = pd.to_datetime(df[date_col]).dt.date

# Per-name daily series, padded (production pre-#3977) and session-true
daily_padded: dict[str, pd.Series] = {}
daily_sess: dict[str, pd.Series] = {}
for u, grp in df.groupby("underlying"):
    s = grp.groupby("_d")["rr"].mean().sort_index()
    daily_padded[str(u)] = s
    daily_sess[str(u)] = s[[d for d in s.index if is_session(d)]]

# ── 0. Replicate the review's 62/350 on the padded store ─────────────────────
fired, evaluated = [], 0
for u, s in daily_padded.items():
    if len(s) >= MIN_OBS_PROD:
        evaluated += 1
        if float(s.iloc[-1]) >= q80(s.values):
            fired.append(u)
R["replication_padded"] = {
    "evaluated": evaluated, "fired": len(fired),
    "rate": round(len(fired) / evaluated, 4) if evaluated else None,
}

# Session-true counts (post-#3977 semantics)
sess_counts = {u: len(s) for u, s in daily_sess.items()}
cohort = sorted(u for u, n in sess_counts.items() if n == 20)
R["session_true"] = {
    "names_at_20_sessions": len(cohort),
    "names_ge_21": sum(1 for n in sess_counts.values() if n >= 21),
    "count_histogram": dict(sorted(Counter(sess_counts.values()).items())),
}

# ── 1. Mechanical null firing rates (iid, finite-n, production quantile) ─────
def sim_null_rates(n_total: int) -> dict:
    """iid standard-normal simulation of each construction's null fire rate."""
    x = rng.standard_normal((N_SIM, n_total))
    hist_loo = x[:, :-1]
    # self-inclusive: last >= Q80(all n)
    thr_self = np.quantile(x, 0.80, axis=1, method="linear")
    p_self = float((x[:, -1] >= thr_self).mean())
    # leave-one-out: last >= Q80(first n-1)
    thr_loo = np.quantile(hist_loo, 0.80, axis=1, method="linear")
    p_loo = float((x[:, -1] >= thr_loo).mean())
    # persistence K of M vs Q80(history excluding last M)
    if n_total > PERSIST_M + 2:
        hist_p = x[:, : n_total - PERSIST_M]
        win = x[:, n_total - PERSIST_M:]
        thr_p = np.quantile(hist_p, 0.80, axis=1, method="linear")
        p_persist = float(((win >= thr_p[:, None]).sum(axis=1) >= PERSIST_K).mean())
    else:
        p_persist = None
    return {"n_total": n_total, "self_inclusive": round(p_self, 4),
            "leave_one_out": round(p_loo, 4),
            f"persist_{PERSIST_K}of{PERSIST_M}": (round(p_persist, 4)
                                                  if p_persist is not None else None)}

R["null_rates_iid"] = {
    "n21": sim_null_rates(21),
    "n26": sim_null_rates(26),
    "n40": sim_null_rates(40),
}

# ── 2+3. Dynamics battery on session-true data, with permutation null ────────
def battery(series_map: dict[str, np.ndarray]) -> dict:
    """Evaluate SELF / LOO / PERSIST day-by-day with expanding history.

    Eval grid (0-indexed day t within each name's session series):
      SELF/LOO eligible at t >= MIN_OBS_MEASURE  (LOO history >= 10)
      PERSIST eligible at t >= MIN_OBS_MEASURE + PERSIST_M - 1 (hist >= 10)
    Returns fire-rate / persistence / run-length / breadth stats.
    """
    fires: dict[str, dict[str, list[tuple[int, bool]]]] = {"self": {}, "loo": {}, "persist": {}}
    for u, v in series_map.items():
        n = len(v)
        if n < MIN_OBS_MEASURE + 1:
            continue
        f_self, f_loo, f_per = [], [], []
        for t in range(MIN_OBS_MEASURE, n):
            f_self.append((t, bool(v[t] >= q80(v[: t + 1]))))
            f_loo.append((t, bool(v[t] >= q80(v[:t]))))
        for t in range(MIN_OBS_MEASURE + PERSIST_M - 1, n):
            hist = v[: t - PERSIST_M + 1]
            win = v[t - PERSIST_M + 1: t + 1]
            f_per.append((t, bool((win >= q80(hist)).sum() >= PERSIST_K)))
        if f_self:
            fires["self"][u] = f_self
            fires["loo"][u] = f_loo
        if f_per:
            fires["persist"][u] = f_per

    out = {}
    for key, per_name in fires.items():
        all_fires = [f for seq in per_name.values() for _, f in seq]
        n_evals = len(all_fires)
        rate = float(np.mean(all_fires)) if n_evals else None
        # pooled persistence over consecutive eval days within name
        num_tt = den_t = 0
        run_lengths = []
        for seq in per_name.values():
            prev = None
            run = 0
            for _, f in seq:
                if prev is True:
                    den_t += 1
                    if f:
                        num_tt += 1
                if f:
                    run += 1
                elif run:
                    run_lengths.append(run)
                    run = 0
                prev = f
            if run:
                run_lengths.append(run)
        p_tt = round(num_tt / den_t, 4) if den_t else None
        # per-day breadth across names
        by_day: dict[int, list[bool]] = {}
        for seq in per_name.values():
            for t, f in seq:
                by_day.setdefault(t, []).append(f)
        breadth = {t: float(np.mean(v)) for t, v in sorted(by_day.items()) if len(v) >= 50}
        b_vals = list(breadth.values())
        out[key] = {
            "n_names": len(per_name), "n_evals": n_evals,
            "fire_rate": round(rate, 4) if rate is not None else None,
            "p_true_given_true": p_tt, "n_transitions_from_true": den_t,
            "mean_true_run": round(float(np.mean(run_lengths)), 3) if run_lengths else None,
            "max_true_run": int(max(run_lengths)) if run_lengths else None,
            "breadth_by_day": {str(k): round(v, 4) for k, v in breadth.items()},
            "breadth_sd": round(float(np.std(b_vals)), 4) if len(b_vals) >= 3 else None,
        }
    return out


obs_map = {u: s.values.astype(float) for u, s in daily_sess.items() if len(s) >= MIN_OBS_MEASURE + 1}
R["observed_battery"] = battery(obs_map)

# Permutation null: shuffle each name's sequence within name (kills temporal
# order and cross-name day alignment; preserves each name's marginal dist).
null_stats: dict[str, dict[str, list[float]]] = {
    k: {"fire_rate": [], "p_true_given_true": [], "mean_true_run": [], "breadth_sd": []}
    for k in ("self", "loo", "persist")
}
for i in range(N_PERM):
    perm_map = {u: rng.permutation(v) for u, v in obs_map.items()}
    b = battery(perm_map)
    for k in null_stats:
        for stat in null_stats[k]:
            val = b.get(k, {}).get(stat)
            if val is not None:
                null_stats[k][stat].append(float(val))
R["permutation_null"] = {
    k: {stat: {"mean": round(float(np.mean(v)), 4), "sd": round(float(np.std(v)), 4),
               "p95": round(float(np.quantile(v, 0.95)), 4)}
        for stat, v in stats.items() if v}
    for k, stats in null_stats.items()
}

# ── 4. rr series structure ────────────────────────────────────────────────────
ac1 = []
for u, v in obs_map.items():
    if len(v) >= 15:
        a = pd.Series(v).autocorr(lag=1)
        if np.isfinite(a):
            ac1.append(float(a))
# Market-factor share: two-way demean on the 20-session full-coverage cohort
panel = pd.DataFrame({u: daily_sess[u] for u in cohort}).dropna(axis=0, how="any")
demeaned = panel.sub(panel.mean(axis=0), axis=1)          # remove name means
day_means = demeaned.mean(axis=1)
var_total = float(demeaned.values.var())
var_day = float(day_means.var() * 1.0)
R["rr_structure"] = {
    "lag1_autocorr_median": round(float(np.median(ac1)), 4),
    "lag1_autocorr_iqr": [round(float(np.quantile(ac1, q)), 4) for q in (0.25, 0.75)],
    "n_names_ac": len(ac1),
    "panel_shape": list(panel.shape),
    "day_factor_var_share": round(var_day / var_total, 4) if var_total else None,
    "day_mean_rr_series": {str(k): round(float(v), 4) for k, v in day_means.items()},
}

# ── 5. Threshold instability at young n ──────────────────────────────────────
shifts, decision_flips = [], 0
for u in cohort:
    v = daily_sess[u].values.astype(float)
    iqr = float(np.quantile(v, 0.75) - np.quantile(v, 0.25))
    t10, t20 = q80(v[:10]), q80(v)
    if iqr > 0:
        shifts.append(abs(t20 - t10) / iqr)
    if (v[-1] >= t10) != (v[-1] >= t20):
        decision_flips += 1
R["threshold_instability"] = {
    "median_abs_shift_q80_first10_vs_all20_in_iqr_units":
        round(float(np.median(shifts)), 4),
    "p90_abs_shift": round(float(np.quantile(shifts, 0.90)), 4),
    "decision_flip_share_last_session": round(decision_flips / len(cohort), 4),
}

# ── 6. Day-1 activation forecast + radar boundary mapping ────────────────────
above_now, persist_now = [], []
for u in cohort:
    v = daily_sess[u].values.astype(float)
    if v[-1] >= q80(v):                      # ~ tomorrow's LOO threshold
        above_now.append(u)
    hist = v[: len(v) - PERSIST_M]
    win = v[len(v) - PERSIST_M:]
    if len(hist) >= MIN_OBS_MEASURE and (win >= q80(hist)).sum() >= PERSIST_K:
        persist_now.append(u)
R["day1_forecast"] = {
    "cohort_n20": len(cohort),
    "share_latest_rr_above_q80_all20": round(len(above_now) / len(cohort), 4),
    "share_persist_3of5_hist15": round(len(persist_now) / len(cohort), 4),
    "persist_prod_eligibility": "hist(excl window)>=21 -> first eval at n>=26 "
                                "(~5 sessions after 2026-07-30)",
}

# Radar boundary cohort under each construction
radar = json.loads(RADAR.read_text())
CROWDED_KEYS = ["extension_extreme", "monthly_rsi_80", "parabolic",
                "valuation_extreme", "analyst_saturated", "call_skew_rich",
                "basket_corr_rising"]
boundary = []
for row in radar["rows"]:
    ch = row["chips"]
    nt = sum(1 for k in CROWDED_KEYS if k != "call_skew_rich" and ch.get(k) is True)
    if nt == 2:
        u = row["ticker"]
        st = {"ticker": u, "state": row["state"], "chip_padded": ch.get("call_skew_rich")}
        if u in daily_sess and len(daily_sess[u]) == 20:
            st["latest_above_q80"] = u in above_now
            st["persist_3of5"] = u in persist_now
        else:
            st["latest_above_q80"] = None
            st["persist_3of5"] = None
        boundary.append(st)
R["radar_boundary_nt2"] = boundary

OUT.write_text(json.dumps(R, indent=2))
print(json.dumps(R, indent=2))
