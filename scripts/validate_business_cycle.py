"""Point-in-time validation of the business-cycle recession signal vs NBER.

The whole point of this harness: the Zeberg/Conference-Board chart LOOKS clean in
hindsight, but a recession-dating rule has only ~7 modern US recessions to learn from
(≈3 inside FRED's 1985+ good-coverage window), gets revised, and throws false positives.
So we MEASURE the signal instead of eyeballing it — and, critically, we measure it
OUT-OF-SAMPLE.

W2.7 (pillar D6) rewrite — what changed and why:
  • LEAVE-ONE-RECESSION-OUT (LORO) calibration (macro-regime-2). The old harness
    grid-searched the threshold/duration on the 1985+ window and then reported the SAME
    window's catch/lead/FP as the shipped "measured" numbers — an in-sample 3/3 on N≈3.
    Now, for each recession we choose the operating point on the OTHERS and score the
    HELD-OUT one. The headline is the pooled OUT-OF-SAMPLE catch/lead/FP with a Jeffreys
    interval on the catch rate — honest about the tiny N. The in-sample full-window fit is
    still computed but LABELLED in-sample and never used as the headline.
  • VINTAGE-AWARE validation (G2). Legs with local ALFRED initial-release vintages
    (engine.business_cycle.VINTAGE_SERIES: ICSA, UMCSENT, PAYEMS, INDPRO) are read at
    their FIRST-published values so the backtest sees what was knowable, not later
    revisions. Legs without vintage coverage stay on revised data and are flagged
    revised=True in the calibration artifact — their leads remain an upper bound. The LIVE
    nowcast keeps latest-revised data (correct for now-casting); only this backtest uses
    initial releases.
  • SYMMETRIC per-leg publication lags (macro-regime-6) are applied by the engine's
    PUB_LAG_M table on BOTH paths; `--extra-lag` stacks a uniform lag on top for stress.

Writes data/regime/business_cycle_calibration.json (LORO-consensus operating point + the
out-of-sample stats the live snapshot ships, with a version + timestamp the live
threshold-override guard checks) and reports/business-cycle-validation.md.

Usage:
    python -m scripts.validate_business_cycle [--start 1985] [--extra-lag 0] [--no-vintage]
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import business_cycle as bc  # noqa: E402
from engine.grading_stats import jeffreys_ci  # noqa: E402
from engine.trial_ledger import register_trials  # noqa: E402
from lib import config  # noqa: E402

# NBER peaks that were exogenous shocks, not slow business-cycle rollovers. A
# leading-indicator model is NOT expected to lead these — flagged, never hidden.
EXOGENOUS_PEAKS = {"2020-02"}


def nber_peaks_troughs(rec: pd.Series) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """(peak, trough) per recession from the monthly USREC flag. USREC=1 begins the
    month AFTER the NBER peak, so peak = the month before the first 1."""
    r = rec.fillna(0).astype(int)
    starts = r.index[(r == 1) & (r.shift(1).fillna(0) == 0)]
    ends = r.index[(r == 1) & (r.shift(-1).fillna(0) == 0)]
    out = []
    for s in starts:
        peak = (s - pd.offsets.MonthEnd(1))
        trough_cands = ends[ends >= s]
        trough = trough_cands[0] if len(trough_cands) else r.index[-1]
        out.append((peak, trough))
    return out


def signal_episodes(sig: pd.Series, merge_gap_m: int = 0) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Maximal runs of True (start = the fire month). With merge_gap_m > 0, runs whose
    gap is <= that many months are consolidated into ONE alarm — so a single jagged
    'growth scare' that dips in and out of the threshold counts once, not five times."""
    s = sig.fillna(False).astype(bool)
    prev = s.shift(1).fillna(False).astype(bool)
    nxt = s.shift(-1).fillna(False).astype(bool)
    starts = list(s.index[s & ~prev])
    ends = list(s.index[s & ~nxt])
    eps = list(zip(starts, ends))
    if merge_gap_m <= 0 or not eps:
        return eps
    merged = [list(eps[0])]
    for st, en in eps[1:]:
        if (st - merged[-1][1]).days / 30.44 <= merge_gap_m:
            merged[-1][1] = en
        else:
            merged.append([st, en])
    return [tuple(m) for m in merged]


def evaluate(frame: pd.DataFrame, threshold: float, diffusion_max: float,
             min_consec: int, max_lead_m: int, lookahead_m: int,
             grace_m: int = 2, merge_gap_m: int = 12, post_rec_grace_m: int = 8,
             holdout_peak: pd.Timestamp | None = None) -> dict:
    """Lead time per recession + (consolidated) false-positive count for one
    (threshold, duration). False alarms are counted as distinct CONSOLIDATED episodes,
    and the early-recovery tail after a trough is exempt (6-month momentum stays
    negative for ~6 months after a V-bottom — an artifact, not a fresh warning).

    LORO seam: when `holdout_peak` is set, the returned `endo_caught`/`mean_lead`/etc are
    computed over the recessions OTHER than the held-out one (the calibration objective),
    while the full per-recession table is retained so the caller can read the held-out
    recession's own catch/lead separately."""
    cfg = config.load()["engine"]["business_cycle"]
    s = dict(cfg["signal"], roc_threshold=threshold, diffusion_max=diffusion_max,
             min_consecutive_m=min_consec)
    sig = bc.recession_signal(frame, dict(cfg, signal=s))["signal"]
    episodes = signal_episodes(sig, merge_gap_m=merge_gap_m)
    rec = frame["nber_recession"]
    peaks = nber_peaks_troughs(rec)
    troughs = [t for _p, t in peaks]

    per_rec = []
    explained_starts: set = set()
    for peak, trough in peaks:
        window_lo = peak - pd.offsets.MonthEnd(max_lead_m)
        window_hi = peak + pd.offsets.MonthEnd(grace_m)
        fires = [st for st, _e in episodes if window_lo <= st <= window_hi]
        pk = str(peak.date())[:7]
        if fires:
            first = min(fires)
            lead = round((peak - first).days / 30.44, 1)
            per_rec.append({"peak": pk, "caught": True, "lead_months": lead,
                            "fired": str(first.date())[:7],
                            "exogenous": pk in EXOGENOUS_PEAKS})
            for st in fires:
                explained_starts.add(st)
        else:
            per_rec.append({"peak": pk, "caught": False, "lead_months": None,
                            "fired": None, "exogenous": pk in EXOGENOUS_PEAKS})

    # false positives: consolidated episodes that neither caught a peak, nor were
    # followed by a recession within lookahead, nor fired during a recession, nor in
    # the early-recovery grace window after a trough.
    false_pos = []
    for st, en in episodes:
        if st in explained_starts:
            continue
        fwd_peak = any(st <= p <= st + pd.offsets.MonthEnd(lookahead_m) for p, _t in peaks)
        in_rec = bool(rec.get(st, 0))
        post_rec = any(t <= st <= t + pd.offsets.MonthEnd(post_rec_grace_m) for t in troughs)
        if not fwd_peak and not in_rec and not post_rec:
            false_pos.append(str(st.date())[:7])

    # scoring pool = endogenous recessions, optionally EXCLUDING the held-out one so the
    # calibration objective is measured only on the training recessions (LORO).
    hp = str(holdout_peak.date())[:7] if holdout_peak is not None else None
    endo = [r for r in per_rec if not r["exogenous"] and r["peak"] != hp]
    endo_caught = [r for r in endo if r["caught"]]
    leads = [r["lead_months"] for r in endo_caught if r["lead_months"] is not None]
    return {
        "threshold": threshold, "diffusion_max": diffusion_max, "min_consecutive_m": min_consec,
        "n_recessions": len(peaks), "n_endogenous": len(endo),
        "endo_caught": len(endo_caught), "false_positives": len(false_pos),
        "fp_dates": false_pos,
        "mean_lead_m": round(float(np.mean(leads)), 1) if leads else None,
        "median_lead_m": round(float(np.median(leads)), 1) if leads else None,
        "per_recession": per_rec,
    }


def _grid(cfg: dict) -> tuple[np.ndarray, tuple]:
    thr_grid = np.round(np.arange(-0.5, -4.01, -0.25), 2)   # 15 thresholds
    mc_grid = (1, 2, 3)                                     # x 3 durations = 45 configs
    return thr_grid, mc_grid


def _pick_best(grid: list[dict], target_lead: float = 6.0, min_lead_floor: float = 3.0) -> dict:
    """Objective (lexicographic): catch the most recessions in the scoring pool, then
    require a credible median lead (>= floor), then fewest false positives, then a lead
    near ~6 months (so the search doesn't chase a loose threshold that 'leads' by a year
    just by firing constantly)."""
    max_caught = max(r["endo_caught"] for r in grid)
    viable = [r for r in grid if r["endo_caught"] == max_caught
              and (r["median_lead_m"] or 0) >= min_lead_floor]
    pool = viable or [r for r in grid if r["endo_caught"] == max_caught]
    return sorted(pool, key=lambda r: (
        r["false_positives"],
        abs((r["median_lead_m"] if r["median_lead_m"] is not None else 0) - target_lead)))[0]


def calibrate_full(frame: pd.DataFrame, cfg: dict) -> tuple[dict, list[dict]]:
    """IN-SAMPLE full-window grid fit — retained for REFERENCE only (labelled in-sample
    in every artifact). This is the old headline; it is no longer shipped as the
    'measured' number. Registers the multiple-testing budget."""
    s = cfg["signal"]
    thr_grid, mc_grid = _grid(cfg)
    register_trials("business_cycle_recession_signal", budget=len(thr_grid) * len(mc_grid),
                    reason="15 roc_thresholds x 3 durations vs NBER (W2.7 LORO recalibration)",
                    basis="itemized")._write()
    grid = [evaluate(frame, float(thr), float(s["diffusion_max"]), mc,
                     int(s["max_lead_window_m"]), int(s["lookahead_window_m"]))
            for thr in thr_grid for mc in mc_grid]
    return _pick_best(grid), grid


def calibrate_loro(frame: pd.DataFrame, cfg: dict) -> dict:
    """Leave-one-recession-out cross-validation.

    For each ENDOGENOUS recession peak R:
      1. choose the operating point by grid search scored on the OTHER endogenous
         recessions only (holdout_peak=R excludes R from the objective);
      2. score that chosen point on the HELD-OUT R: caught? lead? (its false positives
         are a global property of the config, reported for context).
    Returns the pooled OOS results + the LORO-consensus operating point (the config most
    often chosen across holdouts, tie-broken by fewest global FPs then nearest 6m lead)."""
    s = cfg["signal"]
    thr_grid, mc_grid = _grid(cfg)
    peaks = nber_peaks_troughs(frame["nber_recession"])
    endo_peaks = [p for p, _t in peaks if str(p.date())[:7] not in EXOGENOUS_PEAKS]

    per_holdout: list[dict] = []
    chosen_cfgs: list[tuple] = []
    for R in endo_peaks:
        # grid scored EXCLUDING R (train on the other recessions)
        train_grid = [evaluate(frame, float(thr), float(s["diffusion_max"]), mc,
                               int(s["max_lead_window_m"]), int(s["lookahead_window_m"]),
                               holdout_peak=R)
                      for thr in thr_grid for mc in mc_grid]
        best = _pick_best(train_grid)
        chosen_cfgs.append((best["threshold"], best["diffusion_max"], best["min_consecutive_m"]))
        # score the chosen point on the FULL frame, then read R's own row (held out)
        scored = evaluate(frame, best["threshold"], best["diffusion_max"],
                          best["min_consecutive_m"], int(s["max_lead_window_m"]),
                          int(s["lookahead_window_m"]))
        rk = str(R.date())[:7]
        row = next((r for r in scored["per_recession"] if r["peak"] == rk), None)
        per_holdout.append({
            "held_out_peak": rk,
            "train_operating_point": {"roc_threshold": best["threshold"],
                                      "diffusion_max": best["diffusion_max"],
                                      "min_consecutive_m": best["min_consecutive_m"]},
            "train_endo_caught": best["endo_caught"],
            "train_n_endogenous": best["n_endogenous"],
            "oos_caught": bool(row["caught"]) if row else False,
            "oos_lead_months": (row["lead_months"] if row else None),
            "config_false_positives": scored["false_positives"],
        })

    # pooled OOS stats
    n = len(per_holdout)
    k = sum(1 for r in per_holdout if r["oos_caught"])
    oos_leads = [r["oos_lead_months"] for r in per_holdout
                 if r["oos_caught"] and r["oos_lead_months"] is not None]
    catch_ci = jeffreys_ci(k, n) if n else None
    lead_ci = _bootstrap_mean_ci(oos_leads) if len(oos_leads) >= 2 else None

    # LORO-consensus operating point: the config chosen most often across holdouts
    counts = Counter(chosen_cfgs)
    top_cfg, _freq = counts.most_common(1)[0]
    consensus = {"roc_threshold": top_cfg[0], "diffusion_max": top_cfg[1],
                 "min_consecutive_m": top_cfg[2]}
    consensus_scored = evaluate(frame, top_cfg[0], top_cfg[1], top_cfg[2],
                                int(s["max_lead_window_m"]), int(s["lookahead_window_m"]))

    return {
        "method": "LORO",
        "n_endogenous": n,
        "oos_caught": k,
        "oos_catch_rate": round(k / n, 3) if n else None,
        "oos_catch_rate_jeffreys95": list(catch_ci) if catch_ci else None,
        "oos_mean_lead_months": round(float(np.mean(oos_leads)), 1) if oos_leads else None,
        "oos_median_lead_months": round(float(np.median(oos_leads)), 1) if oos_leads else None,
        "oos_mean_lead_boot95": list(lead_ci) if lead_ci else None,
        "per_holdout": per_holdout,
        "consensus_operating_point": consensus,
        "consensus_false_positives": consensus_scored["false_positives"],
        "consensus_fp_dates": consensus_scored["fp_dates"],
    }


def _bootstrap_mean_ci(vals: list[float], draws: int = 5000, seed: int = 7) -> tuple[float, float] | None:
    """Nonparametric bootstrap 95% CI on the mean of a tiny sample (the OOS leads).
    Honest width for N≈3 — an i.i.d. resample of the held-out leads."""
    if len(vals) < 2:
        return None
    a = np.asarray(vals, dtype=float)
    rng = np.random.default_rng(seed)
    means = a[rng.integers(0, len(a), size=(draws, len(a)))].mean(axis=1)
    return (round(float(np.percentile(means, 2.5)), 1),
            round(float(np.percentile(means, 97.5)), 1))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="1985-01-01",
                    help="calibration window start (good leg coverage from ~1985)")
    ap.add_argument("--extra-lag", type=int, default=0,
                    help="extra UNIFORM lag stacked on the per-leg PUB_LAG_M schedule")
    ap.add_argument("--no-vintage", action="store_true",
                    help="disable initial-release vintage reads (revised data everywhere)")
    args = ap.parse_args()

    cfg = config.load()["engine"]["business_cycle"]
    use_vintage = not args.no_vintage
    frame_full = bc.cycle_frame(cfg, lag_m=args.extra_lag, use_vintage=use_vintage)
    if frame_full is None:
        print("no cycle frame — collect FRED series first"); sys.exit(1)
    frame = frame_full.loc[args.start:].dropna(subset=["leading_mom6", "leading_diffusion"])

    # which legs actually ran on vintage (initial-release) vs revised data
    leg_basis = _leg_basis(use_vintage)

    # honest sub-windows: leg coverage thickens ~1985 (orders 1992, HY 1996); the
    # ALFRED point-in-time era is 1997+.
    windows = {
        "full_revised": frame,
        "good_coverage_1985+": frame.loc["1985-01-01":],
        "pit_era_1997+": frame.loc["1997-01-01":],
    }

    # LORO (the honest headline) on the good-coverage window
    loro = calibrate_loro(windows["good_coverage_1985+"], cfg)
    # in-sample full-window fit — REFERENCE ONLY, clearly labelled
    best_in_sample, _grid_rows = calibrate_full(windows["good_coverage_1985+"], cfg)
    in_sample = evaluate(windows["good_coverage_1985+"], best_in_sample["threshold"],
                         best_in_sample["diffusion_max"], best_in_sample["min_consecutive_m"],
                         int(cfg["signal"]["max_lead_window_m"]),
                         int(cfg["signal"]["lookahead_window_m"]))

    # the SHIPPED operating point = the LORO consensus
    op = loro["consensus_operating_point"]
    by_window = {w: evaluate(fr, op["roc_threshold"], op["diffusion_max"],
                             op["min_consecutive_m"], int(cfg["signal"]["max_lead_window_m"]),
                             int(cfg["signal"]["lookahead_window_m"]))
                 for w, fr in windows.items()}

    measured = {
        "method": "LORO",
        "operating_point": op,
        "extra_uniform_lag_m": int(args.extra_lag),
        "vintage_used": use_vintage,
        "leg_basis": leg_basis,
        "calibration_window": f"1985-01-01..present (per-leg publication lags; "
                              f"vintage={'on' if use_vintage else 'off'})",
        # OUT-OF-SAMPLE headline (the honest numbers)
        "oos_endogenous": loro["n_endogenous"],
        "oos_caught": loro["oos_caught"],
        "oos_catch_rate": loro["oos_catch_rate"],
        "oos_catch_rate_jeffreys95": loro["oos_catch_rate_jeffreys95"],
        "oos_mean_lead_months": loro["oos_mean_lead_months"],
        "oos_median_lead_months": loro["oos_median_lead_months"],
        "oos_mean_lead_boot95": loro["oos_mean_lead_boot95"],
        "consensus_false_positives": loro["consensus_false_positives"],
        "per_holdout": loro["per_holdout"],
        # IN-SAMPLE reference (explicitly NOT the headline)
        "in_sample_reference": {
            "operating_point": {"roc_threshold": best_in_sample["threshold"],
                                "diffusion_max": best_in_sample["diffusion_max"],
                                "min_consecutive_m": best_in_sample["min_consecutive_m"]},
            "endo_caught": in_sample["endo_caught"],
            "endo_recessions": in_sample["n_endogenous"],
            "mean_lead_months": in_sample["mean_lead_m"],
            "median_lead_months": in_sample["median_lead_m"],
            "false_positives": in_sample["false_positives"],
            "note": "IN-SAMPLE (fit and scored on the same 1985+ window) — reference only, "
                    "NOT the headline. See out-of-sample stats above.",
        },
        "pit_era_caught": by_window["pit_era_1997+"]["endo_caught"],
        "pit_era_recessions": by_window["pit_era_1997+"]["n_endogenous"],
        "pit_era_false_positives": by_window["pit_era_1997+"]["false_positives"],
        "caveat": ("Out-of-sample (leave-one-recession-out) on N≈3 endogenous recessions — "
                   "even the OOS estimate is underpowered; the Jeffreys interval on the catch "
                   "rate is wide. Vintage (initial-release) data for legs with ALFRED coverage "
                   "(ICSA/UMCSENT/PAYEMS/INDPRO); the rest use revised data so their leads are an "
                   "upper bound. COVID-2020 is exogenous and excluded from lead stats."),
    }

    # persist the calibration the live snapshot reads — with a VERSION + TIMESTAMP the
    # live threshold-override guard checks before it lets this drive the live signal.
    out_cfg = {
        "version": bc.CALIBRATION_VERSION,
        "generated_at": _dt.datetime.now(_dt.timezone.utc).replace(
            microsecond=0, tzinfo=None).isoformat() + "Z",
        "signal": {"roc_threshold": op["roc_threshold"],
                   "diffusion_max": op["diffusion_max"],
                   "min_consecutive_m": op["min_consecutive_m"],
                   "lookahead_window_m": int(cfg["signal"]["lookahead_window_m"]),
                   "max_lead_window_m": int(cfg["signal"]["max_lead_window_m"])},
        "measured": measured,
    }
    cal_path = config.data_dir() / "regime" / "business_cycle_calibration.json"
    cal_path.parent.mkdir(parents=True, exist_ok=True)
    cal_path.write_text(json.dumps(out_cfg, indent=2))

    _write_report(by_window, op, measured, loro, args)
    print(f"\nLORO consensus operating point: threshold={op['roc_threshold']}  "
          f"diffusion<={op['diffusion_max']}  duration={op['min_consecutive_m']}m")
    print(f"  OUT-OF-SAMPLE (LORO): caught {loro['oos_caught']}/{loro['n_endogenous']} "
          f"endogenous (rate {loro['oos_catch_rate']}, Jeffreys95 "
          f"{loro['oos_catch_rate_jeffreys95']}), "
          f"mean lead {loro['oos_mean_lead_months']}m "
          f"(boot95 {loro['oos_mean_lead_boot95']}), "
          f"{loro['consensus_false_positives']} FP")
    print(f"  IN-SAMPLE reference (NOT headline): caught {in_sample['endo_caught']}/"
          f"{in_sample['n_endogenous']}, mean lead {in_sample['mean_lead_m']}m, "
          f"{in_sample['false_positives']} FP")
    print(f"  wrote {cal_path} (version {bc.CALIBRATION_VERSION}) and "
          f"reports/business-cycle-validation.md")


def _leg_basis(use_vintage: bool) -> dict:
    """Per-leg data basis for the artifact: 'vintage' (initial-release) vs 'revised'."""
    out = {}
    for tier, legs in bc.TIERS.items():
        for _g, name, _c, _s in legs:
            has_v = use_vintage and name in bc.VINTAGE_SERIES
            out[name] = {"tier": tier, "basis": "vintage" if has_v else "revised",
                         "revised": not has_v, "pub_lag_m": bc.PUB_LAG_M.get(name, 0)}
    return out


def _fmt_per_rec(rows: list[dict]) -> str:
    lines = ["| NBER peak | caught | lead (months) | first fired | note |",
             "|---|---|---|---|---|"]
    for r in rows:
        note = "exogenous (COVID)" if r["exogenous"] else ""
        caught = "✅" if r["caught"] else "❌ MISS"
        lead = "—" if r["lead_months"] is None else f"{r['lead_months']:+.1f}"
        lines.append(f"| {r['peak']} | {caught} | {lead} | {r['fired'] or '—'} | {note} |")
    return "\n".join(lines)


def _fmt_holdout(rows: list[dict]) -> str:
    lines = ["| held-out recession | train op-point (thr/diff/dur) | OOS caught | OOS lead (m) | config FP |",
             "|---|---|---|---|---|"]
    for r in rows:
        op = r["train_operating_point"]
        ops = f"{op['roc_threshold']} / {op['diffusion_max']:.0f} / {op['min_consecutive_m']}m"
        caught = "✅" if r["oos_caught"] else "❌ MISS"
        lead = "—" if r["oos_lead_months"] is None else f"{r['oos_lead_months']:+.1f}"
        lines.append(f"| {r['held_out_peak']} | {ops} | {caught} | {lead} | {r['config_false_positives']} |")
    return "\n".join(lines)


def _write_report(by_window: dict, op: dict, measured: dict, loro: dict, args) -> None:
    pit = by_window["pit_era_1997+"]
    snap = bc.business_cycle_snapshot()
    cur = ""
    if snap.get("available"):
        rs = snap["recession_signal"]
        lt = snap["tiers"].get("leading", {})
        res = snap.get("calibration_resolution", {})
        cur = (f"\n## Current reading (as of {snap['asof']})\n\n"
               f"- **Recession signal: {rs.get('state', '—').upper()}** — {rs.get('label', '')}.\n"
               f"- Leading 6-month momentum **{lt.get('mom6'):+.2f}** ({lt.get('direction')}), "
               f"diffusion **{lt.get('diffusion'):.0f}** — phase: **{snap['phase']['label']}**.\n"
               f"- Live threshold source: **{res.get('threshold_source', '?')}** "
               f"({res.get('reason', '')}).\n")
    ci = measured["oos_catch_rate_jeffreys95"]
    ci_s = f"[{ci[0]:.2f}, {ci[1]:.2f}]" if ci else "n/a"
    lci = measured["oos_mean_lead_boot95"]
    lci_s = f"[{lci[0]:+.1f}, {lci[1]:+.1f}]" if lci else "n/a"
    isr = measured["in_sample_reference"]
    md = f"""# Business-cycle recession signal — validation vs NBER

_Generated by `scripts/validate_business_cycle.py`. This is a recession-RISK timeline,
not a crash oracle — read the honesty notes. The headline is **out-of-sample** (LORO)._

## Operating point (LORO consensus)

The leading-tier **3 D's** rule (Conference-Board style): fire when the leading index's
**6-month momentum < {op['roc_threshold']}** (depth + duration, in this index's own
standardized units) **and** the **6-month diffusion ≤ {op['diffusion_max']:.0f}**
(breadth), held **{op['min_consecutive_m']} month(s)**. This operating point is the
config **chosen most often across the leave-one-recession-out folds**, not a full-sample
fit. Diffusion is CB-canonical (≤50).

## HEADLINE — out-of-sample (leave-one-recession-out, 1985+)

Each recession is scored by an operating point chosen on the OTHER recessions, so these
numbers are genuinely out-of-sample (not the in-sample 3/3 the old harness reported).

- **OOS endogenous recessions caught:** {measured['oos_caught']} / {measured['oos_endogenous']}
  (rate **{measured['oos_catch_rate']}**, Jeffreys 95% CI **{ci_s}**)
- **OOS mean lead:** {measured['oos_mean_lead_months']} months · **median:** {measured['oos_median_lead_months']} months
  (bootstrap 95% CI on the mean **{lci_s}**)
- **False positives (consensus op-point, full window):** {measured['consensus_false_positives']}

**N≈3 is tiny — even out-of-sample.** The Jeffreys interval above is wide by
construction; treat the point estimate as illustrative, not proof of skill.

### Per-holdout detail (the actual OOS test)

{_fmt_holdout(loro['per_holdout'])}

## In-sample reference (NOT the headline)

For comparison with the old shipped number: a single full-window grid fit on 1985+
chooses threshold **{isr['operating_point']['roc_threshold']}** / duration
**{isr['operating_point']['min_consecutive_m']}m** and — scored on the SAME window it was
fit on — catches **{isr['endo_caught']}/{isr['endo_recessions']}** with mean lead
**{isr['mean_lead_months']}m** and **{isr['false_positives']}** false positives. With only
~3 recessions in-window and a 45-config grid, catching 3/3 in-sample is nearly guaranteed
— which is exactly why it is not the headline.
{cur}

### Point-in-time era (1997+, only ~{pit['n_endogenous']} endogenous recessions)

- **Caught (consensus op-point):** {pit['endo_caught']} / {pit['n_endogenous']} · **false positives:** {pit['false_positives']}
- This is the sample that matters and it is *tiny*. Treat the estimates as illustrative.

## Per-recession detail (full window, consensus op-point)

{_fmt_per_rec(by_window['full_revised']['per_recession'])}

## Data basis per leg (vintage vs revised)

Legs read at their FIRST-published (ALFRED initial-release) values are point-in-time; the
rest use revised data and their leads are an upper bound.

| leg | tier | basis | pub lag (m) |
|---|---|---|---|
""" + "\n".join(
        f"| {name} | {b['tier']} | {b['basis']} | {b['pub_lag_m']} |"
        for name, b in measured["leg_basis"].items()
    ) + f"""

## Honesty notes

- **The headline is out-of-sample (LORO).** The old harness fit and scored on the same
  1985+ window and shipped an in-sample 3/3; that number now lives under "In-sample
  reference" and is explicitly not the headline.
- **Effective N is ~3 endogenous recessions in-window (~2 PIT).** Even LORO is
  underpowered; the Jeffreys interval on the catch rate spans most of [0,1].
- **Vintage handling (G2).** Legs with local ALFRED initial-release vintages
  (ICSA/UMCSENT leading, PAYEMS/INDPRO coincident) are read point-in-time; legs without
  coverage stay on revised data (flagged `revised` above). A keyed CI run with more
  vintage series auto-upgrades more legs.
- **Symmetric publication lags (macro-regime-6).** Each leg carries its real release lag
  (`engine.business_cycle.PUB_LAG_M`), applied on BOTH the live and validation paths —
  not the old "0 live / uniform 1 in the harness". `--extra-lag` was {args.extra_lag}.
- **`cl_ratio` rebase (macro-regime-5)** is anchored to the first-valid value of the
  ratio's own history, so appending months never rewrites the historical level.
- **Threshold-override guard (macro-regime-miss).** The live signal uses this calibration
  JSON only when it is version-matched (`{bc.CALIBRATION_VERSION}`) and fresh; otherwise
  it falls back to the config default and logs a warning. No more silent override.
- **COVID-2020 is exogenous** — excluded from lead statistics.
- **Compare to the conditions layer:** this signal is intentionally separate from the
  `conditions.recession_risk` 0–100 blend; keeping Leading / Coincident / Lagging apart
  is what makes the lead-lag *sequence* legible.
- The chosen threshold is in **this index's units**, deliberately NOT the Conference
  Board's published −4.3% (a differently-scaled index).
"""
    p = config.ROOT / "reports" / "business-cycle-validation.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(md)


if __name__ == "__main__":
    main()
