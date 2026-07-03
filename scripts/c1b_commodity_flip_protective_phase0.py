#!/usr/bin/env python3
"""C1b — Bearish commodity-flip PROTECTIVE demote-gate phase-0 (HK/CA masterplan §4.1, W7-pre).

Pre-reg: research/C1b_COMMODITY_FLIP_PROTECTIVE_PREREG.md (committed BEFORE this run, 757b0b4879).

Two GATED trials, one BH-FDR family, primary horizon 4w, DEMOTE direction (NEGATIVE):
  P1 (sector tier): oil BEAR flip -> XEG excess vs _GSPTSE < 0 (de-rate).
      REUSES the C1 episode machinery VERBATIM (imported from c1_commodity_sector_phase0):
      slope_z / regime_state / confirmed_flips(target=-1) / fwd_excess.
  P2 (name tier, 5y): within CA Energy, HIGH oil-beta minus LOW oil-beta forward differential
      D = ret_EW(HIGH) - ret_EW(LOW) < 0, with POINT-IN-TIME oil-beta (no look-ahead), tercile
      HIGH/LOW split per episode, non-overlapping greedy windows, suspension-honest.

Gate (H4 demote bar): HAC t <= -2.0 AND BH-FDR reject AND split-half same-sign-negative AND N>=8.
DSR on the PROTECTIVE Sharpe (sign-flipped series) at TrialLedger.with_declared_budget(36, family).
NO WIRING.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.validation import (  # noqa: E402
    newey_west_tstat, benjamini_hochberg, bootstrap_effective_t, deflated_sharpe,
)
from engine.trial_ledger import TrialLedger, register_trials  # noqa: E402
# --- reuse C1 episode construction VERBATIM (no re-definition, no shopping) ---
from scripts.c1_commodity_sector_phase0 import (  # noqa: E402
    slope_z, regime_state, confirmed_flips, raw_flip_count, fwd_excess, _load,
    HORIZONS, PRIMARY_H, DSR_BLOCK,
)

# ---- frozen pre-reg constants (C1b-specific) ---------------------------------
N_TRIALS = 36            # program budget now ~=36 (prompt / masterplan §6, ledger-declared)
FAMILY = "c1b_commodity_flip_protective_phase0"
_LED = TrialLedger.with_declared_budget(N_TRIALS, FAMILY)
SPLIT_SECTOR = pd.Timestamp("2013-01-01")   # C1's a-priori split (P1 full history)
SPLIT_NAME = pd.Timestamp("2023-12-31")     # panel midpoint for the 5y name tier (P2)
W_BETA = 252             # PIT beta trailing window (name tier)
BETA_MINOBS = 120        # min overlap for a PIT beta at an episode
NAME_MIN_XS = 9          # min qualifying Energy names to keep an episode

DATA_C = ROOT / "data" / "canada"
DATA_Y = ROOT / "data" / "yahoo"
DATA_S = ROOT / "data" / "canada_search"


# ---------------- P1: sector tier (reuses C1 fwd_excess verbatim) -------------
def sector_trial(commodity, etf, bench):
    logp = np.log(commodity)
    state = regime_state(slope_z(logp))
    flips = confirmed_flips(state, target=-1)          # BEAR flips
    raw = raw_flip_count(state, target=-1)
    out = {"name": "P1 oil BEAR->XEG", "raw_flips": raw,
           "confirmed_flips": len(flips), "horizons": {}}
    for hlabel, H in HORIZONS.items():
        ep, daily = fwd_excess(etf, bench, flips, H)   # non-overlap, next-bar, susp-honest
        out["horizons"][hlabel] = _stats(ep, daily, SPLIT_SECTOR)
    return out


# ---------------- P2: name tier (PIT oil-beta, HIGH-LOW differential) ---------
def _pit_oil_beta(name_ret: pd.Series, mkt_ret: pd.Series, oil_ret: pd.Series,
                  asof: pd.Timestamp) -> float | None:
    """Market-controlled oil-beta over the trailing W_BETA sessions ENDING at `asof`
    (inclusive). No forward data. Mirrors engine/canada_factor_beta lstsq design."""
    df = pd.concat({"y": name_ret, "mkt": mkt_ret, "oil": oil_ret}, axis=1).dropna()
    df = df[df.index <= asof]
    if len(df) < BETA_MINOBS:
        return None
    df = df.iloc[-W_BETA:]
    if len(df) < BETA_MINOBS:
        return None
    y = df["y"].to_numpy()
    X = np.column_stack([np.ones(len(df)), df["mkt"].to_numpy(), df["oil"].to_numpy()])
    try:
        coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    except Exception:  # noqa: BLE001
        return None
    return float(coef[2])  # oil coefficient


def _basket_fwd_ret(closes: pd.DataFrame, tickers: list[str],
                    fill_date: pd.Timestamp, end_date: pd.Timestamp) -> float | None:
    """Equal-weight forward total return of `tickers` over [fill_date, end_date],
    suspension-honest (each name uses its own present first/last bar in the window;
    a name with <2 present bars in the window is dropped from the basket)."""
    rets = []
    for t in tickers:
        s = closes[t].loc[fill_date:end_date].dropna()
        if len(s) < 2:
            continue
        rets.append(s.iloc[-1] / s.iloc[0] - 1.0)
    if not rets:
        return None
    return float(np.mean(rets))


def name_trial(commodity, closes: pd.DataFrame, energy: list[str],
               mkt_close: pd.Series, oil_close: pd.Series):
    logp = np.log(commodity)
    state = regime_state(slope_z(logp))
    flips = confirmed_flips(state, target=-1)          # BEAR flips (same events as P1)
    raw = raw_flip_count(state, target=-1)

    cidx = closes.index
    name_rets = closes.pct_change(fill_method=None)
    mkt_ret = mkt_close.reindex(cidx).pct_change(fill_method=None)
    oil_ret = oil_close.reindex(cidx).pct_change(fill_method=None)

    out = {"name": "P2 Energy HIGH-LOW oil-beta", "raw_flips": raw,
           "confirmed_flips_in_panel": 0, "horizons": {}, "xs_sizes": []}

    # restrict flips to those inside the name panel (need trailing beta + fwd window)
    panel_flips = [f for f in flips if cidx.min() <= f <= cidx.max()]
    out["confirmed_flips_in_panel"] = len(panel_flips)

    for hlabel, H in HORIZONS.items():
        eps = []           # (fill_date, D)
        daily_D = []       # daily differential inside window (for t_eff)
        claimed_until = -1
        xs_sizes = []
        pos_all = cidx.searchsorted(pd.DatetimeIndex(panel_flips), side="right")
        for k, p in enumerate(pos_all):
            if p >= len(cidx) or p <= claimed_until:
                continue
            end = p + H
            if end >= len(cidx):
                continue                                # window past data end -> drop
            t0 = panel_flips[k]                          # flip-confirmation day
            fill_date, end_date = cidx[p], cidx[end]
            # PIT beta per Energy name using data up to t0 (fill is t0's next bar)
            betas = {}
            for t in energy:
                b = _pit_oil_beta(name_rets[t], mkt_ret, oil_ret, t0)
                if b is not None:
                    betas[t] = b
            if len(betas) < NAME_MIN_XS:
                continue                                # thin cross-section -> drop episode
            ser = pd.Series(betas).sort_values()        # ascending oil-beta
            n = len(ser)
            k_ter = max(1, n // 3)
            low = list(ser.index[:k_ter])               # bottom tercile = LOW beta
            high = list(ser.index[-k_ter:])             # top tercile = HIGH beta
            r_hi = _basket_fwd_ret(closes, high, fill_date, end_date)
            r_lo = _basket_fwd_ret(closes, low, fill_date, end_date)
            if r_hi is None or r_lo is None:
                continue
            D = r_hi - r_lo
            eps.append((fill_date, D))
            xs_sizes.append(n)
            # daily differential inside window for t_eff
            hi_d = name_rets[high].iloc[p + 1:end + 1].mean(axis=1)
            lo_d = name_rets[low].iloc[p + 1:end + 1].mean(axis=1)
            daily_D.append((hi_d - lo_d).dropna())
            claimed_until = end
        ep = pd.Series({d: v for d, v in eps}).sort_index() if eps else pd.Series(dtype=float)
        daily = pd.concat(daily_D) if daily_D else pd.Series(dtype=float)
        row = _stats(ep, daily, SPLIT_NAME)
        row["median_xs"] = int(np.median(xs_sizes)) if xs_sizes else None
        out["horizons"][hlabel] = row
    return out


# ---------------- shared stats (protective/NEGATIVE framing) ------------------
def _stats(ep: pd.Series, daily: pd.Series, split_date: pd.Timestamp) -> dict:
    n = len(ep)
    row = {"n_episodes": n}
    if n < 3:
        return row
    nw = newey_west_tstat(ep.values, lags=4)
    row.update(mean=nw["mean"], hac_se=nw["se"], hac_t=nw["t"], hac_p=nw["p"])
    row["hit_neg"] = round(float((ep < 0).mean()), 3)   # protective hit = fraction negative
    teff = bootstrap_effective_t(daily, block=DSR_BLOCK) if len(daily) >= 60 else {}
    row["t_eff"] = teff.get("t_eff")
    row["t_eff_raw"] = teff.get("t_raw")
    # DSR on the PROTECTIVE (sign-flipped) series: -ep. A real de-rate => positive protective SR.
    prot = -ep.values
    m, sd = float(prot.mean()), float(prot.std(ddof=1))
    if sd > 0 and n >= 4:
        from scipy.stats import skew as _sk, kurtosis as _ku
        sr = m / sd
        dsr = deflated_sharpe(sr, float(_sk(prot)), float(_ku(prot, fisher=False)),
                              T=n, ledger=_LED, family=FAMILY,
                              t_eff=teff.get("t_eff") if teff else None)
        row["sr_protective"] = round(sr, 4)
        row["dsr_protective"] = dsr["dsr"] if dsr else None
    if n >= 6:
        rng = np.random.default_rng(11)
        boots = np.array([rng.choice(ep.values, n, replace=True).mean() for _ in range(5000)])
        row["mean_ci90"] = [round(float(np.percentile(boots, 5)), 5),
                            round(float(np.percentile(boots, 95)), 5)]
        row["mean_lt0_prob"] = round(float((boots < 0).mean()), 3)  # P(de-rate)
    pre = ep[ep.index < split_date]
    post = ep[ep.index >= split_date]
    row["split"] = {
        "pre_n": len(pre), "pre_mean": round(float(pre.mean()), 5) if len(pre) else None,
        "post_n": len(post), "post_mean": round(float(post.mean()), 5) if len(post) else None,
        "same_sign_neg": (len(pre) > 0 and len(post) > 0 and
                          pre.mean() < 0 and post.mean() < 0),
    }
    row["episodes"] = [(str(d.date()), round(float(v), 4)) for d, v in ep.items()]
    return row


def verdict(row) -> str:
    """H4 DEMOTE-gate verdict at primary horizon (pre-reg §5)."""
    if row.get("n_episodes", 0) < 3 or row.get("hac_t") is None:
        return "NO-GO (insufficient episodes)"
    t = row["hac_t"]; m = row["mean"]; n = row["n_episodes"]
    dsr = row.get("dsr_protective")
    same = row.get("split", {}).get("same_sign_neg", False)
    if t >= 2.0:
        return "KILL (significantly POSITIVE — protective premise backwards)"
    if m >= 0:
        return "NO-GO (non-negative mean — no de-rate)"
    if not same:
        return "NO-GO (split-half sign flip)"
    go = (t <= -2.0 and same and n >= 8)   # + FDR checked at family level, stamped in report
    if go:
        return "GO-for-DEMOTE (H4 bar; FDR verified in family)"
    if (m < 0) and (t <= -1.0 or (dsr is not None and dsr >= 0.50)):
        return "ACCRUE"
    return "NO-GO"


@register_trials(FAMILY, budget=N_TRIALS, basis="estimated",
                 reason="masterplan §6 program-level DSR budget (~36, both markets); C1b adds 2 gated")
def main():
    cl = _load(DATA_Y / "CL_F.parquet")
    bench = _load(DATA_C / "_GSPTSE.parquet")
    xeg = _load(DATA_C / "XEG.TO.parquet")

    p1 = sector_trial(cl, xeg, bench)

    closes = pd.read_parquet(DATA_S / "closes.parquet")
    closes.index = pd.to_datetime(closes.index)
    closes = closes.sort_index()
    members = pd.read_parquet(DATA_S / "members.parquet")
    energy = [t for t in members[members["sector"] == "Energy"].index if t in closes.columns]
    p2 = name_trial(cl, closes, energy, bench, cl)

    # BH-FDR across the 2 gated trials at primary horizon (one-sided toward NEGATIVE)
    pvals = {}
    for tr in (p1, p2):
        r = tr["horizons"][PRIMARY_H]
        if r.get("hac_p") is not None:
            two = r["hac_p"]
            one = two / 2 if (r.get("mean", 0) or 0) < 0 else 1 - two / 2
            pvals[tr["name"]] = one
    bh = benjamini_hochberg(pvals, alpha=0.10) if pvals else {}

    import json
    print(json.dumps({
        "P1_sector": p1, "P2_name": p2,
        "energy_universe_n": len(energy), "energy": energy,
        "bh_fdr_primary": bh, "pvals_onesided_neg": pvals,
        "verdicts": {p1["name"]: verdict(p1["horizons"][PRIMARY_H]),
                     p2["name"]: verdict(p2["horizons"][PRIMARY_H])},
        "params": {"w_beta": W_BETA, "beta_minobs": BETA_MINOBS, "name_min_xs": NAME_MIN_XS,
                   "primary_h": PRIMARY_H, "n_trials": N_TRIALS,
                   "split_sector": str(SPLIT_SECTOR.date()), "split_name": str(SPLIT_NAME.date())},
    }, indent=2, default=str))


if __name__ == "__main__":
    import logging
    logging.disable(logging.CRITICAL)
    main()
