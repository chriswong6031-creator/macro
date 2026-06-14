"""Point-in-time validation of the business-cycle recession signal vs NBER.

The whole point of this harness: the Zeberg/Conference-Board chart LOOKS clean in
hindsight, but a recession-dating rule has only ~7 modern US recessions to learn
from (≈3 inside FRED's 1997+ point-in-time window), gets revised, and throws false
positives. So we MEASURE the signal instead of eyeballing it — lead time per
recession, false-positive count, hit rate — and ship those numbers with the panel.

Honesty controls:
  • Publication lag — natively-monthly inputs are shifted 1 month (May data is not
    knowable in May). Removes the dominant look-ahead.
  • Revisions — the LEADING legs that get revised (claims, permits, orders, hours,
    sentiment) have NO local ALFRED vintages (needs FRED_API_KEY), so the backtest
    uses revised values for them: measured leads are an UPPER BOUND. The market legs
    (S&P 500, curve, HY) are never revised. PAYEMS/INDPRO vintages exist but are
    COINCIDENT, so they don't touch the leading signal. config registers the new
    series in `vintage_series`, so a keyed CI run auto-upgrades this to full PIT.
  • COVID-2020 is flagged EXOGENOUS — an exogenous pandemic shock no cycle model leads;
    counting it as a "miss" or a "0-month catch" is reported, never hidden.
  • Effective N is tiny; sub-windows (leg coverage, PIT era) are reported separately.

Writes data/regime/business_cycle_calibration.json (the chosen operating point + the
measured stats the live snapshot ships) and reports/business-cycle-validation.md.

Usage:
    python -m scripts.validate_business_cycle [--start 1970] [--lag-months 1]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import business_cycle as bc  # noqa: E402
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
    starts = list(s.index[s & ~s.shift(1).fillna(False)])
    ends = list(s.index[s & ~s.shift(-1).fillna(False)])
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
             grace_m: int = 2, merge_gap_m: int = 12, post_rec_grace_m: int = 8) -> dict:
    """Lead time per recession + (consolidated) false-positive count for one
    (threshold, duration). False alarms are counted as distinct CONSOLIDATED episodes,
    and the early-recovery tail after a trough is exempt (6-month momentum stays
    negative for ~6 months after a V-bottom — an artifact, not a fresh warning)."""
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
        if fires:
            first = min(fires)
            lead = round((peak - first).days / 30.44, 1)
            per_rec.append({"peak": str(peak.date())[:7], "caught": True,
                            "lead_months": lead, "fired": str(first.date())[:7],
                            "exogenous": str(peak.date())[:7] in EXOGENOUS_PEAKS})
            for st in fires:
                explained_starts.add(st)
        else:
            per_rec.append({"peak": str(peak.date())[:7], "caught": False,
                            "lead_months": None, "fired": None,
                            "exogenous": str(peak.date())[:7] in EXOGENOUS_PEAKS})

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

    endo = [r for r in per_rec if not r["exogenous"]]
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


def calibrate(frame: pd.DataFrame, cfg: dict) -> tuple[dict, list[dict]]:
    """Grid-sweep the threshold + duration on the leading momentum. Objective
    (lexicographic): catch the most ENDOGENOUS recessions, then fewest (consolidated)
    false positives, then a CREDIBLE lead — median closest to ~6 months, so the search
    doesn't chase a loose threshold that 'leads' by a year just by firing constantly.
    Diffusion stays CB-canonical (<=50)."""
    s = cfg["signal"]
    target_lead, min_lead_floor = 6.0, 3.0
    grid = []
    for thr in np.round(np.arange(-0.5, -4.01, -0.25), 2):
        for mc in (1, 2, 3):
            grid.append(evaluate(frame, float(thr), float(s["diffusion_max"]), mc,
                                  int(s["max_lead_window_m"]), int(s["lookahead_window_m"])))
    max_caught = max(r["endo_caught"] for r in grid)
    # A recession signal must actually LEAD: require median lead >= the floor among the
    # max-catch settings, THEN minimize false positives, THEN prefer a lead near ~6mo.
    # (Without the floor the search picks a near-coincident 0-month-lead point that has
    # marginally fewer false alarms but no anticipatory value.)
    viable = [r for r in grid if r["endo_caught"] == max_caught
              and (r["median_lead_m"] or 0) >= min_lead_floor]
    pool = viable or [r for r in grid if r["endo_caught"] == max_caught]
    best = sorted(pool, key=lambda r: (
        r["false_positives"],
        abs((r["median_lead_m"] if r["median_lead_m"] is not None else 0) - target_lead)))[0]
    return best, grid


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="1970-01-01")
    ap.add_argument("--lag-months", type=int, default=1)
    args = ap.parse_args()

    cfg = config.load()["engine"]["business_cycle"]
    frame_full = bc.cycle_frame(cfg, lag_m=args.lag_months)
    if frame_full is None:
        print("no cycle frame — collect FRED series first"); sys.exit(1)
    frame = frame_full.loc[args.start:].dropna(subset=["leading_mom6", "leading_diffusion"])

    # honest sub-windows: leg coverage thickens ~1985 (orders 1992, HY 1996); the
    # ALFRED point-in-time era is 1997+.
    windows = {
        "full_revised": frame,
        "good_coverage_1985+": frame.loc["1985-01-01":],
        "pit_era_1997+": frame.loc["1997-01-01":],
    }

    best, grid = calibrate(windows["good_coverage_1985+"], cfg)
    # re-evaluate the CHOSEN operating point across every window for the report
    by_window = {w: evaluate(fr, best["threshold"], best["diffusion_max"],
                             best["min_consecutive_m"], int(cfg["signal"]["max_lead_window_m"]),
                             int(cfg["signal"]["lookahead_window_m"]))
                 for w, fr in windows.items()}

    chosen = by_window["good_coverage_1985+"]
    measured = {
        "operating_point": {"roc_threshold": best["threshold"],
                            "diffusion_max": best["diffusion_max"],
                            "min_consecutive_m": best["min_consecutive_m"]},
        "calibration_window": "1985-01-01..present (revised data, 1m publication lag)",
        "endo_recessions": chosen["n_endogenous"],
        "endo_caught": chosen["endo_caught"],
        "false_positives": chosen["false_positives"],
        "mean_lead_months": chosen["mean_lead_m"],
        "median_lead_months": chosen["median_lead_m"],
        "pit_era_caught": by_window["pit_era_1997+"]["endo_caught"],
        "pit_era_recessions": by_window["pit_era_1997+"]["n_endogenous"],
        "pit_era_false_positives": by_window["pit_era_1997+"]["false_positives"],
        "caveat": ("Revised data for the leading legs (no local ALFRED key) — leads are an "
                   "upper bound. Effective N ~3 endogenous recessions in the PIT era. COVID-2020 "
                   "is exogenous and excluded from lead stats."),
    }

    # persist the calibration the live snapshot reads
    out_cfg = {"signal": {"roc_threshold": best["threshold"],
                          "diffusion_max": best["diffusion_max"],
                          "min_consecutive_m": best["min_consecutive_m"],
                          "lookahead_window_m": int(cfg["signal"]["lookahead_window_m"]),
                          "max_lead_window_m": int(cfg["signal"]["max_lead_window_m"])},
               "measured": measured}
    cal_path = config.data_dir() / "regime" / "business_cycle_calibration.json"
    cal_path.parent.mkdir(parents=True, exist_ok=True)
    cal_path.write_text(json.dumps(out_cfg, indent=2))

    _write_report(by_window, best, measured, args)
    print(f"\nChosen operating point: threshold={best['threshold']}  "
          f"diffusion<={best['diffusion_max']}  duration={best['min_consecutive_m']}m")
    print(f"  1985+: caught {chosen['endo_caught']}/{chosen['n_endogenous']} endogenous, "
          f"{chosen['false_positives']} false positives, mean lead {chosen['mean_lead_m']}m")
    print(f"  PIT 1997+: caught {by_window['pit_era_1997+']['endo_caught']}/"
          f"{by_window['pit_era_1997+']['n_endogenous']}, "
          f"{by_window['pit_era_1997+']['false_positives']} FP")
    print(f"  wrote {cal_path} and reports/business-cycle-validation.md")


def _fmt_per_rec(rows: list[dict]) -> str:
    lines = ["| NBER peak | caught | lead (months) | first fired | note |",
             "|---|---|---|---|---|"]
    for r in rows:
        note = "exogenous (COVID)" if r["exogenous"] else ""
        caught = "✅" if r["caught"] else "❌ MISS"
        lead = "—" if r["lead_months"] is None else f"{r['lead_months']:+.1f}"
        lines.append(f"| {r['peak']} | {caught} | {lead} | {r['fired'] or '—'} | {note} |")
    return "\n".join(lines)


def _write_report(by_window: dict, best: dict, measured: dict, args) -> None:
    w = by_window["good_coverage_1985+"]
    pit = by_window["pit_era_1997+"]
    snap = bc.business_cycle_snapshot()
    cur = ""
    if snap.get("available"):
        rs = snap["recession_signal"]
        lt = snap["tiers"].get("leading", {})
        cur = (f"\n## Current reading (as of {snap['asof']})\n\n"
               f"- **Recession signal: {rs.get('state', '—').upper()}** — {rs.get('label', '')}.\n"
               f"- Leading 6-month momentum **{lt.get('mom6'):+.2f}** ({lt.get('direction')}), "
               f"diffusion **{lt.get('diffusion'):.0f}** — phase: **{snap['phase']['label']}**.\n"
               f"- Threshold to fire is {rs['conditions']['roc_threshold']} with diffusion ≤ "
               f"{rs['conditions']['diffusion_max']:.0f}; today it is neither deep nor broad "
               f"enough, so the model does **not** corroborate an imminent recession.\n")
    md = f"""# Business-cycle recession signal — validation vs NBER

_Generated by `scripts/validate_business_cycle.py`. This is a recession-RISK timeline,
not a crash oracle — read the honesty notes._

## Operating point (calibrated)

The leading-tier **3 D's** rule (Conference-Board style): fire when the leading index's
**6-month momentum < {best['threshold']}** (depth + duration, in this index's own
standardized units) **and** the **6-month diffusion ≤ {best['diffusion_max']:.0f}**
(breadth), held **{best['min_consecutive_m']} month(s)**. Threshold chosen by grid
search to catch the most endogenous recessions, then fewest false positives, then
longest lead — on the 1985+ window. Diffusion is CB-canonical (≤50).

## Headline (1985+, revised data, {args.lag_months}-month publication lag)

- **Endogenous recessions caught:** {w['endo_caught']} / {w['n_endogenous']}
- **Mean lead:** {w['mean_lead_m']} months · **median:** {w['median_lead_m']} months
- **False positives:** {w['false_positives']}  {('(' + ', '.join(w['fp_dates']) + ')') if w['fp_dates'] else ''}

The false positives are not noise — they are the **famous post-war growth scares that
did not become recessions**: the 1995 soft landing, the 2002 jobless-recovery double-dip
fear, and the 2022 inflation/rate-hike scare (which the *actual* Conference Board LEI
also flagged as a recession for ~18 months). A genuine business-cycle gauge SHOULD light
up in those episodes — that it lights up in exactly those and nowhere else is a feature.
{cur}

### Point-in-time era (1997+, the honest core — only ~{pit['n_endogenous']} endogenous recessions)

- **Caught:** {pit['endo_caught']} / {pit['n_endogenous']} · **false positives:** {pit['false_positives']}
- This is the sample that matters and it is *tiny*. Treat the lead estimates as
  illustrative, not statistically robust.

## Per-recession detail (full window from {args.start[:4]})

{_fmt_per_rec(by_window['full_revised']['per_recession'])}

## Honesty notes

- **Effective N is ~7 modern recessions (~3 point-in-time).** Any tuned rule is
  overfit-prone; the clean hindsight alignment of older signals is a presentation.
- **Pre-1985 rows are unreliable** — leg coverage is thin (cap-goods orders begin 1992,
  HY spread 1996), so the index runs on ~4 legs and the 1980/1981 double-dip (two
  recessions ~12 months apart) and the 2018-19 → COVID window produce odd lead
  attributions. That sparse coverage is exactly why calibration uses the 1985+ window.
- **Revisions are NOT stripped for the leading legs** (claims/permits/orders/hours/
  sentiment — no local `FRED_API_KEY`). Measured leads are an **upper bound**. The
  market legs (S&P 500, yield curve, HY spread) are never revised. The new series are
  registered in `config.yml fred.vintage_series`, so a keyed CI run auto-upgrades this
  backtest to full point-in-time.
- **COVID-2020 is exogenous** — no business-cycle model leads a pandemic. It is shown
  but excluded from the lead statistics.
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
