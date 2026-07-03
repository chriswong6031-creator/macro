"""H5 — HK peg-liquidity regime conditioner. Phase-0 battery (masterplan §3 H5).

CONDITIONER-GRADE ONLY: sizes HK exposure, never ranks names. Bar = directional
consistency + drawdown separation + split-half sign stability, NOT DSR>=0.90.
Frozen construction per research/HK_CANADA_H5_PREREG.md (committed before this ran).

Two decision trials:
  (a) PRIMARY   : SOFR-era 2018-04-> , USD leg = SOFR
  (b) SECONDARY : spliced 2002-> , USD leg = DFF pre-2018 spliced to SOFR (labeled)
Plus a labeled exploratory southbound-interaction pass and robustness variants.

Reports only. No wiring into any live engine or board. logging.disable under __main__.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from lib import store
from engine.validation import (
    newey_west_tstat,
    benjamini_hochberg,
    deflated_sharpe,
    bootstrap_effective_t,
    block_bootstrap_ci,
)
from engine.trial_ledger import register_trials

log = logging.getLogger("h5")

# ---- frozen construction constants (mirror the pre-reg §3) ------------------- #
PCT_WIN = 252          # trailing business days for own-history percentile
E_EASY = 33.0          # composite ease-score threshold for EASY
E_TIGHT = -33.0        # ... for TIGHT
DEBOUNCE_OPEN = 10     # bd a label must persist to open an episode
DEBOUNCE_GAP = 5       # bd opposite/neutral interruption tolerated inside an episode
STALE_CAP_BD = 3       # usd/hkma forward-fill staleness cap (business days)
HORIZONS = {"1m": 21, "3m": 63}
PROGRAM_N_TRIALS = 30  # masterplan §6 program-level DSR budget (both markets)
SOFR_START = pd.Timestamp("2018-04-02")


# --------------------------------------------------------------------------- #
# Data loaders
# --------------------------------------------------------------------------- #
def load_hkma() -> pd.DataFrame:
    df = pd.read_parquet("data/hkma/interbank_liquidity.parquet")
    df = df[["agg_balance", "hibor_on", "hibor_1m"]].astype(float).sort_index()
    df.index = pd.to_datetime(df.index)
    return df


def load_usd_leg() -> tuple[pd.Series, pd.Series]:
    """Return (sofr, dff) daily rate series (percent)."""
    sofr = store.read("ofr", "FNYR-SOFR-A")
    sofr = sofr.iloc[:, 0].astype(float).dropna()
    sofr.index = pd.to_datetime(sofr.index)
    dff = store.read("fred", "DFF")
    dff = dff.iloc[:, 0].astype(float).dropna()
    dff.index = pd.to_datetime(dff.index)
    return sofr.sort_index(), dff.sort_index()


def load_hsi() -> pd.Series:
    df = pd.read_parquet("data/hk/_HSI.parquet")
    s = df["close"].astype(float).dropna()
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def load_southbound() -> pd.Series:
    df = pd.read_parquet("data/china_connect/southbound.parquet")
    s = df["net"].astype(float).dropna()
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


# --------------------------------------------------------------------------- #
# Regime construction
# --------------------------------------------------------------------------- #
def _reindex_stale_capped(src: pd.Series, target_idx: pd.DatetimeIndex) -> pd.Series:
    """Forward-fill src onto target trading days, but treat any value staler than
    STALE_CAP_BD *calendar-adjacent source observations* as missing. We approximate
    'business-day staleness' by counting source rows: ffill then blank where the last
    real observation is > STALE_CAP_BD source-days behind the target date."""
    # align on union, ffill, then null out stale
    s = src.reindex(src.index.union(target_idx)).sort_index()
    ff = s.ffill()
    # date of last real (non-NaN pre-ffill) observation for each row
    last_real = pd.Series(np.where(s.notna(), s.index, pd.NaT), index=s.index).ffill()
    last_real = pd.to_datetime(last_real)
    age_days = (s.index.to_series() - last_real).dt.days
    ff = ff.where(age_days <= STALE_CAP_BD * 2, np.nan)  # *2: calendar cushion on 3 bd
    return ff.reindex(target_idx)


def build_regime(hkma: pd.DataFrame, usd_leg: pd.Series) -> pd.DataFrame:
    """Frozen §3 construction. Returns a frame indexed on HKMA trading days with
    spread, composite ease-score E, and the EASY/TIGHT/NEUTRAL label."""
    idx = hkma.index
    usd = _reindex_stale_capped(usd_leg, idx)
    spread = hkma["hibor_1m"] - usd                       # pp; HIBOR minus USD leg
    bal = hkma["agg_balance"]

    def roll_pct(s: pd.Series) -> pd.Series:
        # percentile rank of the LAST value within the trailing PCT_WIN window (0-100)
        return s.rolling(PCT_WIN, min_periods=60).apply(
            lambda w: (w <= w[-1]).mean() * 100.0, raw=True)

    bal_pct = roll_pct(bal)
    spread_pct = roll_pct(spread)
    E = bal_pct - spread_pct                               # high = easy
    label = pd.Series("NEUTRAL", index=idx, dtype=object)
    label[E >= E_EASY] = "EASY"
    label[E <= E_TIGHT] = "TIGHT"
    label[E.isna()] = np.nan
    out = pd.DataFrame({"spread": spread, "bal_pct": bal_pct,
                        "spread_pct": spread_pct, "E": E, "label": label})
    return out


def debounce_episodes(label: pd.Series) -> list[dict]:
    """§3 episode definition: maximal same-label runs, open only if persists
    >=DEBOUNCE_OPEN bd, with <=DEBOUNCE_GAP bd opposite/neutral interruptions
    tolerated (hysteresis). Returns list of {label,start,end,n_days}."""
    lab = label.dropna()
    if lab.empty:
        return []
    episodes: list[dict] = []
    i = 0
    dates = lab.index
    vals = lab.values
    n = len(vals)
    while i < n:
        cur = vals[i]
        if cur == "NEUTRAL":
            i += 1
            continue
        # extend while same label, tolerating small gaps of != cur
        j = i
        last_same = i
        gap = 0
        k = i + 1
        while k < n:
            if vals[k] == cur:
                last_same = k
                gap = 0
            else:
                gap += 1
                if gap > DEBOUNCE_GAP:
                    break
            k += 1
        run_days = last_same - i + 1  # count of days from open to last confirming day
        if run_days >= DEBOUNCE_OPEN:
            episodes.append({"label": cur, "start": dates[i], "end": dates[last_same],
                             "n_days": int(run_days)})
        i = last_same + 1
    return episodes


# --------------------------------------------------------------------------- #
# Forward returns + regime contrast
# --------------------------------------------------------------------------- #
def forward_returns(hsi: pd.Series, ref_idx: pd.DatetimeIndex, h: int) -> pd.Series:
    """Next-bar-lagged forward return over h trading bars, on ACTUAL closes only
    (no ffill across gaps). Entry = next available HSI close after each ref date;
    exit = the close h bars later. Windows that run past data end are dropped."""
    hsi = hsi.sort_index()
    hidx = hsi.index
    pos = hidx.searchsorted(ref_idx, side="right")  # first HSI bar strictly after ref
    out = {}
    hv = hsi.values
    for ref, p in zip(ref_idx, pos):
        if p < len(hv) and p + h < len(hv):
            r = hv[p + h] / hv[p] - 1.0
            out[ref] = float(r)
    return pd.Series(out).sort_index()


def _maxdd(equity_ret: np.ndarray) -> float:
    if len(equity_ret) == 0:
        return 0.0
    eq = np.cumprod(1.0 + equity_ret)
    peak = np.maximum.accumulate(eq)
    return float(((eq - peak) / peak).min())


def regime_daily_strategy(label: pd.Series, hsi: pd.Series, target: str) -> pd.Series:
    """Daily HSI log-simple returns on days labeled `target` (else flat=0).
    Used for bootstrap_effective_t / block_bootstrap_ci / maxdd of the conditioner."""
    hsi = hsi.sort_index()
    daily = hsi.pct_change()
    lab = label.reindex(daily.index).ffill(limit=STALE_CAP_BD)
    strat = daily.where(lab == target, 0.0).fillna(0.0)
    return strat


def contrast(regime: pd.DataFrame, hsi: pd.Series, window_start=None, window_end=None) -> dict:
    """Full EASY-vs-TIGHT contrast at both horizons on the given window."""
    lab = regime["label"].copy()
    if window_start is not None:
        lab = lab[lab.index >= window_start]
    if window_end is not None:
        lab = lab[lab.index <= window_end]
    lab = lab.dropna()
    easy_days = lab.index[lab == "EASY"]
    tight_days = lab.index[lab == "TIGHT"]

    res = {"n_easy_days": int(len(easy_days)), "n_tight_days": int(len(tight_days)),
           "n_neutral_days": int((lab == "NEUTRAL").sum()), "horizons": {}}

    for hname, h in HORIZONS.items():
        fe = forward_returns(hsi, easy_days, h)
        ft = forward_returns(hsi, tight_days, h)
        if len(fe) < 8 or len(ft) < 8:
            res["horizons"][hname] = {"insufficient": True,
                                      "n_easy": len(fe), "n_tight": len(ft)}
            continue
        # HAC t on each mean, and on the difference via pooled sign-flipped stack
        nw_e = newey_west_tstat(fe.values, lags=h - 1)
        nw_t = newey_west_tstat(ft.values, lags=h - 1)
        # difference: stack EASY (+) and TIGHT-negated; the mean of the stacked series
        # equals (mean_easy - mean_tight)/1 only if balanced — instead compute the
        # HAC t of the difference by demeaning within group then testing the gap via
        # the two independent HAC ses (conservative).
        diff = nw_e["mean"] - nw_t["mean"]
        se_diff = np.sqrt((nw_e["se"] or 0) ** 2 + (nw_t["se"] or 0) ** 2)
        t_diff = diff / se_diff if se_diff > 0 else float("nan")
        res["horizons"][hname] = {
            "n_easy": int(len(fe)), "n_tight": int(len(ft)),
            "mean_easy": round(float(fe.mean()), 5), "mean_tight": round(float(ft.mean()), 5),
            "diff_easy_minus_tight": round(float(diff), 5),
            "t_easy": nw_e["t"], "t_tight": nw_t["t"],
            "t_diff": round(float(t_diff), 3),
            "p5_easy": round(float(np.percentile(fe, 5)), 5),
            "p5_tight": round(float(np.percentile(ft, 5)), 5),
            "min_easy": round(float(fe.min()), 5), "min_tight": round(float(ft.min()), 5),
            "median_easy": round(float(fe.median()), 5),
            "median_tight": round(float(ft.median()), 5),
        }
    return res


def strategy_metrics(regime: pd.DataFrame, hsi: pd.Series, target: str,
                     window_start=None, window_end=None) -> dict:
    lab = regime["label"]
    if window_start is not None:
        lab = lab[lab.index >= window_start]
    if window_end is not None:
        lab = lab[lab.index <= window_end]
    strat = regime_daily_strategy(lab, hsi, target)
    strat = strat[strat.index >= (window_start or strat.index.min())]
    arr = strat.values
    active = strat[strat != 0.0]
    m = {"maxdd_pct": round(_maxdd(arr) * 100.0, 2),
         "n_active_days": int((strat != 0.0).sum())}
    bt = bootstrap_effective_t(active) if len(active) >= 60 else {}
    ci = block_bootstrap_ci(active) if len(active) >= 60 else {}
    m["t_eff"] = bt.get("t_eff")
    m["t_raw"] = bt.get("t_raw")
    m["boot_ci"] = ci
    return m


# --------------------------------------------------------------------------- #
# Trials
# --------------------------------------------------------------------------- #
def run_trial(name: str, hkma: pd.DataFrame, usd_leg: pd.Series, hsi: pd.Series,
              window_start=None) -> dict:
    regime = build_regime(hkma, usd_leg)
    if window_start is not None:
        regime = regime[regime.index >= window_start]
    episodes = debounce_episodes(regime["label"])
    ep_easy = [e for e in episodes if e["label"] == "EASY"]
    ep_tight = [e for e in episodes if e["label"] == "TIGHT"]

    con = contrast(regime, hsi)
    sm_easy = strategy_metrics(regime, hsi, "EASY")
    sm_tight = strategy_metrics(regime, hsi, "TIGHT")

    # split-half sign stability at 3m
    dates = regime["label"].dropna().index
    mid = dates[len(dates) // 2]
    con_h1 = contrast(regime, hsi, window_end=mid)
    con_h2 = contrast(regime, hsi, window_start=mid)

    # DSR (program n_trials=30) on the EASY-minus-TIGHT daily overlay strategy:
    # go long HSI in EASY, short in TIGHT (the conditioner's implied timing).
    lab = regime["label"]
    daily = hsi.pct_change().reindex(lab.index)
    overlay = pd.Series(0.0, index=lab.index)
    overlay[lab == "EASY"] = daily[lab == "EASY"]
    overlay[lab == "TIGHT"] = -daily[lab == "TIGHT"]
    overlay = overlay.dropna()
    dsr = None
    if len(overlay) >= 60:
        bt = bootstrap_effective_t(overlay)
        sr_d = overlay.mean() / overlay.std(ddof=1) if overlay.std(ddof=1) > 0 else 0.0
        dsr = deflated_sharpe(
            sr_daily=float(sr_d), skew=float(overlay.skew()),
            kurt=float(overlay.kurtosis() + 3.0), T=len(overlay),
            n_trials=PROGRAM_N_TRIALS, t_eff=bt.get("t_eff"))

    return {
        "name": name,
        "window": [str(regime.index.min().date()), str(regime.index.max().date())],
        "n_episodes_easy": len(ep_easy), "n_episodes_tight": len(ep_tight),
        "episodes_easy": [{"start": str(e["start"].date()), "end": str(e["end"].date()),
                           "n_days": e["n_days"]} for e in ep_easy],
        "episodes_tight": [{"start": str(e["start"].date()), "end": str(e["end"].date()),
                            "n_days": e["n_days"]} for e in ep_tight],
        "contrast": con,
        "strategy_easy": sm_easy, "strategy_tight": sm_tight,
        "split_half": {"first": con_h1["horizons"].get("3m", {}),
                       "second": con_h2["horizons"].get("3m", {}),
                       "mid_date": str(mid.date())},
        "dsr_overlay": dsr,
    }


def splice_usd_leg(sofr: pd.Series, dff: pd.Series) -> tuple[pd.Series, dict]:
    """SECONDARY: DFF before 2018-04-02, SOFR from 2018-04-02. Report the basis."""
    pre = dff[dff.index < SOFR_START]
    post = sofr[sofr.index >= SOFR_START]
    spliced = pd.concat([pre, post]).sort_index()
    spliced = spliced[~spliced.index.duplicated(keep="last")]
    # SOFR-DFF basis over the overlap (2018-04->) for discontinuity honesty
    ov = sofr.index.intersection(dff.index)
    basis = (sofr.reindex(ov) - dff.reindex(ov)).dropna()
    binfo = {"n_overlap_days": int(len(basis)),
             "mean_sofr_minus_dff_bp": round(float(basis.mean() * 100), 2),
             "std_bp": round(float(basis.std() * 100), 2),
             "p5_bp": round(float(np.percentile(basis, 5) * 100), 2),
             "p95_bp": round(float(np.percentile(basis, 95) * 100), 2)}
    return spliced, binfo


def exploratory_southbound(regime: pd.DataFrame, sb: pd.Series) -> dict:
    """Labeled, non-gated: is southbound net flow stronger in EASY vs TIGHT?"""
    lab = regime["label"].reindex(sb.index).ffill(limit=STALE_CAP_BD)
    ov = sb.index.intersection(lab.dropna().index)
    sbo = sb.reindex(ov)
    labo = lab.reindex(ov)
    easy = sbo[labo == "EASY"]
    tight = sbo[labo == "TIGHT"]
    return {
        "overlap": [str(ov.min().date()), str(ov.max().date())] if len(ov) else None,
        "n_easy_days": int(len(easy)), "n_tight_days": int(len(tight)),
        "mean_net_easy": round(float(easy.mean()), 2) if len(easy) else None,
        "mean_net_tight": round(float(tight.mean()), 2) if len(tight) else None,
        "median_net_easy": round(float(easy.median()), 2) if len(easy) else None,
        "median_net_tight": round(float(tight.median()), 2) if len(tight) else None,
        "pct_days_positive_easy": round(float((easy > 0).mean() * 100), 1) if len(easy) else None,
        "pct_days_positive_tight": round(float((tight > 0).mean() * 100), 1) if len(tight) else None,
    }


def robustness(hkma, sofr, hsi) -> dict:
    """R1 O/N HIBOR; R2 thresholds; R3 balance-only / spread-only. Reported, not gated."""
    out = {}
    # R1: use O/N HIBOR instead of 1m
    idx = hkma.index
    usd = _reindex_stale_capped(sofr, idx)
    for tag, hib in (("R1_on_hibor", hkma["hibor_on"]), ("base_1m", hkma["hibor_1m"])):
        spread = hib - usd
        def rp(s):
            return s.rolling(PCT_WIN, min_periods=60).apply(lambda w: (w <= w[-1]).mean() * 100, raw=True)
        E = rp(hkma["agg_balance"]) - rp(spread)
        lab = pd.Series("NEUTRAL", index=idx, dtype=object)
        lab[E >= E_EASY] = "EASY"; lab[E <= E_TIGHT] = "TIGHT"; lab[E.isna()] = np.nan
        reg = pd.DataFrame({"label": lab})
        reg = reg[reg.index >= SOFR_START]
        c = contrast(reg, hsi)
        out[tag] = {h: {"diff": c["horizons"][h].get("diff_easy_minus_tight"),
                        "t_diff": c["horizons"][h].get("t_diff")}
                    for h in HORIZONS if not c["horizons"][h].get("insufficient")}
    # R2: thresholds +-25 / +-40
    spread = hkma["hibor_1m"] - usd
    def rp(s):
        return s.rolling(PCT_WIN, min_periods=60).apply(lambda w: (w <= w[-1]).mean() * 100, raw=True)
    Ebase = rp(hkma["agg_balance"]) - rp(spread)
    for thr in (25.0, 40.0):
        lab = pd.Series("NEUTRAL", index=idx, dtype=object)
        lab[Ebase >= thr] = "EASY"; lab[Ebase <= -thr] = "TIGHT"; lab[Ebase.isna()] = np.nan
        reg = pd.DataFrame({"label": lab}); reg = reg[reg.index >= SOFR_START]
        c = contrast(reg, hsi)
        out[f"R2_thr{int(thr)}"] = {h: {"diff": c["horizons"][h].get("diff_easy_minus_tight"),
                                        "t_diff": c["horizons"][h].get("t_diff")}
                                    for h in HORIZONS if not c["horizons"][h].get("insufficient")}
    # R3: balance-only and spread-only composites
    for tag, E in (("R3_bal_only", rp(hkma["agg_balance"]) - 50.0),
                   ("R3_spread_only", 50.0 - rp(spread))):
        lab = pd.Series("NEUTRAL", index=idx, dtype=object)
        lab[E >= E_EASY] = "EASY"; lab[E <= E_TIGHT] = "TIGHT"; lab[E.isna()] = np.nan
        reg = pd.DataFrame({"label": lab}); reg = reg[reg.index >= SOFR_START]
        c = contrast(reg, hsi)
        out[tag] = {h: {"diff": c["horizons"][h].get("diff_easy_minus_tight"),
                        "t_diff": c["horizons"][h].get("t_diff")}
                    for h in HORIZONS if not c["horizons"][h].get("insufficient")}
    return out


@register_trials("h5_peg_liquidity_phase0", budget=PROGRAM_N_TRIALS, basis="estimated",
                 reason="masterplan §6 program-level DSR budget (both markets)")
def main() -> dict:
    hkma = load_hkma()
    sofr, dff = load_usd_leg()
    hsi = load_hsi()
    sb = load_southbound()

    # PRIMARY trial (a): SOFR-era 2018->
    primary = run_trial("PRIMARY_sofr_2018", hkma, sofr, hsi, window_start=SOFR_START)

    # SECONDARY trial (b): spliced 2002->
    spliced, basis = splice_usd_leg(sofr, dff)
    secondary = run_trial("SECONDARY_spliced_2002", hkma, spliced, hsi, window_start=None)
    secondary["splice_basis_sofr_minus_dff"] = basis
    # flag episodes straddling the splice boundary
    straddle = [e for e in
                (secondary["episodes_easy"] + secondary["episodes_tight"])
                if e["start"] < "2018-04-02" <= e["end"]]
    secondary["episodes_straddling_splice"] = straddle

    # BH-FDR across the 2 decision trials (t_diff@3m -> two-sided p via normal)
    def p_from_t(t):
        from math import erf, sqrt
        return 2 * (1 - 0.5 * (1 + erf(abs(t) / sqrt(2))))
    pvals = {}
    for tr in (primary, secondary):
        h3 = tr["contrast"]["horizons"].get("3m", {})
        if "t_diff" in h3:
            pvals[tr["name"]] = p_from_t(h3["t_diff"])
    fdr = benjamini_hochberg(pvals, alpha=0.10) if pvals else {}

    # exploratory southbound (on the PRIMARY-window regime, using SOFR leg)
    reg_primary = build_regime(hkma, sofr)
    reg_primary = reg_primary[reg_primary.index >= SOFR_START]
    explo = exploratory_southbound(reg_primary, sb)

    rob = robustness(hkma, sofr, hsi)

    return {
        "built": datetime.now(timezone.utc).isoformat(),
        "config": {"pct_win": PCT_WIN, "E_easy": E_EASY, "E_tight": E_TIGHT,
                   "debounce_open": DEBOUNCE_OPEN, "debounce_gap": DEBOUNCE_GAP,
                   "stale_cap_bd": STALE_CAP_BD, "horizons": HORIZONS,
                   "program_n_trials": PROGRAM_N_TRIALS},
        "primary": primary, "secondary": secondary,
        "fdr": fdr, "pvals": pvals,
        "exploratory_southbound": explo,
        "robustness": rob,
    }


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    out = main()
    print(json.dumps(out, indent=2, default=str))
