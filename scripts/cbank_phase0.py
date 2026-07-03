#!/usr/bin/env python3
"""C-BANK phase-0 battery — bank-earnings-season clustering + PEAD.

Pre-registered in research/CBANK_PREREG.md (committed BEFORE this ran).
Trials frozen there; this file only EXECUTES them. Reports-only (no wiring).

Season leg (H-C-BANK-1): XFN.TO / ZEB.TO excess over _GSPTSE inside vs outside
fixed ±2w bank-earnings-season windows, aggregated to non-overlapping season-quarter
EPISODES. PEAD leg (H-C-BANK-2): per-bank sector-neutral forward drift, beat vs miss.

Stats: HAC (newey_west_tstat), DSR (deflated_sharpe, n_trials=30), bootstrap_effective_t,
BH-FDR within family, split-half sign-stability. NEXT-BAR fills.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))
from engine.validation import (  # noqa: E402
    newey_west_tstat, deflated_sharpe, bootstrap_effective_t,
    benjamini_hochberg, ret_moments, dsr_verdict,
)
from engine.trial_ledger import TrialLedger, register_trials  # noqa: E402

N_TRIALS_PROGRAM = 30          # masterplan §6 program-level DSR count, ledger-declared floor
FAMILY = "cbank_phase0"
_LED = TrialLedger.with_declared_budget(N_TRIALS_PROGRAM, FAMILY)
ANCHORS = {"Feb": (2, 25), "May": (5, 28), "Aug": (8, 27), "Dec": (12, 3)}
WIN_DAYS = 14                  # ± calendar days around anchor
BANKS = ["RY.TO", "TD.TO", "BMO.TO", "BNS.TO", "CM.TO"]  # NA.TO absent (verified)


def _load_close(name: str) -> pd.Series:
    d = pd.read_parquet(ROOT / f"data/canada/{name}.parquet")
    s = d["close"].dropna()
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def _logret(s: pd.Series) -> pd.Series:
    return np.log(s / s.shift(1))


def _in_season_mask(idx: pd.DatetimeIndex) -> pd.Series:
    """True on days within ±WIN_DAYS of any seasonal anchor."""
    m = pd.Series(False, index=idx)
    for (mo, day) in ANCHORS.values():
        for yr in range(idx.min().year, idx.max().year + 1):
            try:
                anchor = pd.Timestamp(year=yr, month=mo, day=day)
            except ValueError:
                continue
            lo, hi = anchor - pd.Timedelta(days=WIN_DAYS), anchor + pd.Timedelta(days=WIN_DAYS)
            m |= (idx >= lo) & (idx <= hi)
    return m


def _season_episodes(excess: pd.Series):
    """Aggregate daily excess into non-overlapping (year, season) episodes.
    Returns (in_episodes, out_episodes) as arrays of compounded excess returns."""
    idx = excess.index
    in_eps, out_eps = [], []
    years = range(idx.min().year, idx.max().year + 1)
    anchors_sorted = []
    for yr in years:
        for (mo, day) in ANCHORS.values():
            try:
                anchors_sorted.append(pd.Timestamp(year=yr, month=mo, day=day))
            except ValueError:
                pass
    anchors_sorted = sorted(anchors_sorted)
    # in-window episodes
    for anchor in anchors_sorted:
        lo, hi = anchor - pd.Timedelta(days=WIN_DAYS), anchor + pd.Timedelta(days=WIN_DAYS)
        seg = excess[(idx >= lo) & (idx <= hi)].dropna()
        if len(seg) >= 3:                      # need a real window present in data
            in_eps.append(float(seg.sum()))    # log-excess sum = compounded
    # out-window episodes = the inter-anchor gaps (one per gap)
    for a0, a1 in zip(anchors_sorted[:-1], anchors_sorted[1:]):
        gap_lo = a0 + pd.Timedelta(days=WIN_DAYS + 1)
        gap_hi = a1 - pd.Timedelta(days=WIN_DAYS + 1)
        seg = excess[(idx >= gap_lo) & (idx <= gap_hi)].dropna()
        if len(seg) >= 3:
            out_eps.append(float(seg.sum()))
    return np.array(in_eps), np.array(out_eps)


def _split_half_sign(in_eps, out_eps, dates_in):
    """Sign of (mean_in - mean_out) in each calendar half (split by median in-episode date)."""
    med = dates_in[len(dates_in) // 2] if len(dates_in) else None
    if med is None or len(in_eps) < 6:
        return None
    early = np.array([e for e, d in zip(in_eps, dates_in) if d <= med])
    late = np.array([e for e, d in zip(in_eps, dates_in) if d > med])
    out_mean = out_eps.mean() if len(out_eps) else 0.0
    s_e = np.sign(early.mean() - out_mean) if len(early) else 0
    s_l = np.sign(late.mean() - out_mean) if len(late) else 0
    return {"early_sign": int(s_e), "late_sign": int(s_l),
            "agree": bool(s_e == s_l and s_e != 0),
            "early_mean_pct": round(100 * float(early.mean()), 3) if len(early) else None,
            "late_mean_pct": round(100 * float(late.mean()), 3) if len(late) else None}


def season_trial(etf: str):
    xfn = _load_close(etf)
    gsp = _load_close("_GSPTSE")
    df = pd.concat({"e": _logret(xfn), "m": _logret(gsp)}, axis=1).dropna()
    excess = (df["e"] - df["m"]).dropna()          # daily log-excess (div-drift is constant, cancels in-out)
    mask = _in_season_mask(excess.index)
    in_daily = excess[mask.values]
    out_daily = excess[~mask.values]

    # episode-level (primary)
    # dates of in-window episodes (anchor dates that have data)
    in_eps, out_eps = _season_episodes(excess)
    # anchor dates present (for split-half)
    idx = excess.index
    anchors_present = []
    for yr in range(idx.min().year, idx.max().year + 1):
        for (mo, day) in ANCHORS.values():
            try:
                a = pd.Timestamp(year=yr, month=mo, day=day)
            except ValueError:
                continue
            lo, hi = a - pd.Timedelta(days=WIN_DAYS), a + pd.Timedelta(days=WIN_DAYS)
            if ((idx >= lo) & (idx <= hi)).sum() >= 3:
                anchors_present.append(a)
    anchors_present = sorted(anchors_present)

    # contrast series: in-episodes minus the pooled out-mean → test mean != 0 via HAC
    out_mean = out_eps.mean() if len(out_eps) else 0.0
    contrast = in_eps - out_mean
    hac = newey_west_tstat(contrast, lags=2)       # episodes ~quarterly, mild AC

    # DSR: use the DAILY in-window excess as the "strategy" return (long sleeve inside windows only),
    # net of out-of-window mean drift, so DSR measures the season edge not the dividend carry.
    strat_daily = (in_daily - out_daily.mean())
    mom = ret_moments(strat_daily)                 # (sharpe, skew, kurt, n) or None
    teff = bootstrap_effective_t(strat_daily, block=10)
    if mom is not None:
        sr_daily, skew, kurt, _ = mom
        dsr = deflated_sharpe(sr_daily, skew, kurt, T=len(strat_daily),
                              ledger=_LED, family=FAMILY,
                              t_eff=teff.get("t_eff") if teff else None)
    else:
        dsr = None

    sh = _split_half_sign(in_eps, out_eps, anchors_present)
    return {
        "etf": etf,
        "n_in_episodes": int(len(in_eps)), "n_out_episodes": int(len(out_eps)),
        "in_mean_pct": round(100 * float(in_eps.mean()), 4) if len(in_eps) else None,
        "out_mean_pct": round(100 * float(out_eps.mean()), 4) if len(out_eps) else None,
        "contrast_mean_pct": round(100 * float(contrast.mean()), 4),
        "hac_t": hac["t"], "hac_p": hac["p"], "hac_n": hac["n"],
        "dsr": dsr["dsr"] if dsr else None, "sr_annual": dsr["sr_annual"] if dsr else None,
        "t_eff": teff.get("t_eff") if teff else None, "t_raw": teff.get("t_raw") if teff else None,
        "split_half": sh,
    }


def _bank_events():
    e = pd.read_parquet(ROOT / "data/canada_earnings/earnings.parquet").set_index("ticker")
    rows = []
    for b in BANKS:
        if b not in e.index:
            continue
        p = json.loads(e.loc[b, "payload"])
        for s in p["surprises"]:
            rows.append({"bank": b, "date": pd.Timestamp(s["date"]),
                         "surp": float(s["surprise_pct"])})
    return pd.DataFrame(rows)


def pead_trials():
    ev = _bank_events()
    panel = pd.read_parquet(ROOT / "data/canada_search/closes.parquet")
    panel.index = pd.to_datetime(panel.index)
    xfn = _load_close("XFN.TO")
    lo, hi = panel.index.min(), panel.index.max()
    horizons = {"1w": 5, "2w": 10, "4w": 20}

    per_horizon = {h: {"beat": [], "miss": [], "events": 0, "dropped": 0} for h in horizons}
    for _, r in ev.iterrows():
        b, d, surp = r["bank"], r["date"], r["surp"]
        if b not in panel.columns:
            continue
        s = panel[b].dropna()
        # next-bar fill: first available session strictly after report date
        after = s.index[s.index > d]
        if len(after) == 0:
            continue
        fill_bars = after[:1]
        # suspension rule: fill within +3 sessions else drop
        if (fill_bars[0] - d).days > 5:   # ~3 trading sessions
            for h in horizons:
                per_horizon[h]["dropped"] += 1
            continue
        f0 = fill_bars[0]
        for h, td in horizons.items():
            pos = s.index.get_loc(f0)
            if pos + td >= len(s):
                continue
            p0, p1 = s.iloc[pos], s.iloc[pos + td]
            bank_ret = np.log(p1 / p0)
            # sector-neutralize by XFN over same calendar span
            xf = xfn.reindex(s.index).ffill()
            xr = np.log(xf.iloc[pos + td] / xf.iloc[pos]) if not np.isnan(xf.iloc[pos]) else 0.0
            drift = float(bank_ret - xr)
            (per_horizon[h]["beat" if surp > 0 else "miss"]).append(drift)
            per_horizon[h]["events"] += 1

    out = {}
    for h, dd in per_horizon.items():
        beat, miss = np.array(dd["beat"]), np.array(dd["miss"])
        # beat-miss contrast: build a signed pooled series (beats +, misses flipped) for HAC on mean-diff
        # HAC on the concatenation of (beat - grand) vs (miss - grand) is not a diff test; use the
        # difference-in-means with a pooled HAC se via the stacked deviations.
        if len(beat) >= 2 and len(miss) >= 2:
            diff = float(beat.mean() - miss.mean())
            # pooled series for HAC se of the difference: center each group, HAC on beats gives se_b,
            # simple combine (independent groups) → se = sqrt(se_b^2 + se_m^2)
            hb = newey_west_tstat(beat, lags=1)
            hm = newey_west_tstat(miss, lags=1)
            se = float(np.hypot(hb["se"], hm["se"])) if hb["se"] and hm["se"] else None
            t = diff / se if se else None
            p = round(2 * (1 - _ncdf(abs(t))), 4) if t is not None else None
        else:
            diff = t = p = None
        out[h] = {"beat_n": int(len(beat)), "miss_n": int(len(miss)),
                  "beat_mean_pct": round(100 * float(beat.mean()), 3) if len(beat) else None,
                  "miss_mean_pct": round(100 * float(miss.mean()), 3) if len(miss) else None,
                  "diff_pct": round(100 * diff, 3) if diff is not None else None,
                  "hac_t": round(t, 3) if t is not None else None, "hac_p": p,
                  "events": dd["events"], "dropped": dd["dropped"]}
    return out


def _ncdf(x):
    from math import erf, sqrt
    return 0.5 * (1 + erf(x / sqrt(2)))


def exploratory():
    """E1/E2: does the season effect extend to rate-sensitive sleeves (labeled, non-gated)."""
    out = {}
    for etf in ["XUT.TO", "XRE.TO"]:
        try:
            r = season_trial(etf)
            out[etf] = {"n_in": r["n_in_episodes"], "contrast_pct": r["contrast_mean_pct"],
                        "hac_t": r["hac_t"], "dsr": r["dsr"]}
        except Exception as ex:
            out[etf] = {"error": str(ex)}
    return out


@register_trials("cbank_phase0", budget=N_TRIALS_PROGRAM, basis="estimated",
                 reason="masterplan §6 program-level DSR budget (both markets)")
def main():
    import logging
    logging.disable(logging.CRITICAL)   # under __main__ only

    season = {"XFN.TO": season_trial("XFN.TO"), "ZEB.TO": season_trial("ZEB.TO")}
    pead = pead_trials()
    expl = exploratory()

    # BH-FDR within families
    season_p = {k: v["hac_p"] for k, v in season.items() if v["hac_p"] is not None}
    pead_p = {h: pead[h]["hac_p"] for h in pead if pead[h]["hac_p"] is not None}
    bh_season = benjamini_hochberg(season_p, alpha=0.10)
    bh_pead = benjamini_hochberg(pead_p, alpha=0.10)

    result = {"season": season, "pead": pead, "exploratory": expl,
              "bh_season": bh_season, "bh_pead": bh_pead,
              "n_trials_program": N_TRIALS_PROGRAM,
              "dsr_verdict_xfn": dsr_verdict(season["XFN.TO"]["dsr"]) if season["XFN.TO"]["dsr"] else None}
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
