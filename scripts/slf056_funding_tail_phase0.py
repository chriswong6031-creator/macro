"""Phase-0 validation: SLF-056 — repo/SOFR tail stress as a de-escalation-gate input.

HYPOTHESIS: The existing engine/funding_stress.py composite (SOFR–EFFR spread
percentile + p99 SOFR dispersion percentile, averaged to a 0-100 score) carries
forward-looking information about equity drawdown risk and bond direction.
Specifically, high composite scores precede SPY drawdowns and negative TLT returns,
suggesting the composite could serve as a de-escalation gating input (not a score).

CURRENT STATUS: CONTEXT-ONLY (engine/funding_stress.py is display-only, never wired
into any score). This harness tests whether it EARNS promotion to de-escalation-gate
INPUT status.

SIGNALS UNDER TEST (exactly as specified, computed via engine functions where possible):
  - composite: 0-100 score = avg(spread_pctile, disp_pctile), using 504-day rolling window
  - spread_pctile: SOFR–EFFR spread trailing-window percentile (one leg)
  - disp_pctile: SOFR p99 − SOFR dispersion percentile (other leg)

TESTS:
  T1: AUC of signal level vs 'SPY enters a >=5% drawdown within 21d/63d'
  T2: Same vs TLT 21d forward return sign (positive = bonds rally)
  T3: Event study on band transitions into 'stressed' (score crosses 90 from below)

GATES (ALL computed before looking at results — pre-registered):
  G1: AUC >= 0.60 with block-bootstrap 90% CI excluding 0.50 at >=1 horizon
  G2: Leave-one-episode-out: sign/direction stable across all three removals
      Episodes: Sep-2019 repo spike, Mar-2020 COVID, Mar-2023 SVB
  G3: Beats a dumb VIX>25 baseline AUC on the same panel

ALL GATES PASS -> recommend de-escalation-gate input status (still not scored).
ANY FAIL -> CONTEXT ruling reaffirmed, print the null.

PIT DISCIPLINE:
  - OFR reference rates are PUBLISHED on business day T (end-of-day); used from T+1 onward.
    This is the publication-lag assumption enforced: all signals shift(1) before comparison.
  - SPY/TLT prices from Yahoo are close prices; forward returns/drawdowns computed strictly
    in the future (no look-ahead).
  - VIX close prices from FRED VIXCLS: same T+1 convention as OFR data.

HONEST CONSTRAINT:
  - 2018+ sample has ~3 genuine funding-stress episodes. Every statistic carries
    leave-one-episode-out sensitivity analysis.
  - N is tiny — we report all numbers including the null. This study is CONCLUSIVE
    at the small-n level: no retroactive expansion of sample.

Run:  python -m scripts.slf056_funding_tail_phase0
Writes: reports/slf056-funding-tail-phase0.md

Trial family: slf056_funding_tail (3 signals x 2 horizons = 6 core trials)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.validation import block_bootstrap_ci          # noqa: E402
from engine.trial_ledger import TrialLedger               # noqa: E402

# --------------------------------------------------------------------------- #
# CONSTANTS
# --------------------------------------------------------------------------- #
FAMILY = "slf056_funding_tail"
PCTILE_LOOKBACK = 504        # 2y trading days, matches engine default
COST_BPS = 0.0               # AUC test — no trading cost

# Pre-registered episodes for leave-one-out
EPISODES = {
    "sep2019_repo": ("2019-09-01", "2019-10-31"),
    "mar2020_covid": ("2020-02-15", "2020-05-31"),
    "mar2023_svb":   ("2023-03-01", "2023-05-31"),
}

# AUC horizons
HORIZONS_T1 = [21, 63]   # SPY drawdown entry
HORIZONS_T2 = [21]       # TLT return sign

# Gate thresholds (pre-registered, never changed after looking at results)
AUC_GATE = 0.60
AUC_BASELINE = 0.50   # CI must exclude 0.50


# --------------------------------------------------------------------------- #
# TRIAL LEDGER — log ALL configs AT GENERATION, before any backtest
# --------------------------------------------------------------------------- #
def _register_trials(ledger: TrialLedger) -> None:
    """Log the full config grid at generation — 3 signals x (2+1) tests x 2 horizons
    for T1/T2 = 18 configs; plus event-study T3 for each signal = 3 more.
    Total: 21 distinct trials. Log them all now."""
    signals = ["composite", "spread_pctile", "disp_pctile"]
    # T1 configs
    for sig in signals:
        for h in HORIZONS_T1:
            ledger.log_trial(
                {"signal": sig, "test": "T1_auc_spy_drawdown", "horizon_d": h,
                 "drawdown_thresh": -0.05, "pctile_lookback": PCTILE_LOOKBACK},
                family=FAMILY, info_cutoff="2026-06-30",
                note="AUC vs SPY >=5% drawdown entry"
            )
    # T2 configs
    for sig in signals:
        for h in HORIZONS_T2:
            ledger.log_trial(
                {"signal": sig, "test": "T2_auc_tlt_return_sign", "horizon_d": h,
                 "pctile_lookback": PCTILE_LOOKBACK},
                family=FAMILY, info_cutoff="2026-06-30",
                note="AUC vs TLT 21d return sign"
            )
    # T3 event study — band transition into stressed (score >= 90)
    for sig in signals:
        ledger.log_trial(
            {"signal": sig, "test": "T3_event_study_stressed_entry", "band_thresh": 90,
             "pctile_lookback": PCTILE_LOOKBACK},
            family=FAMILY, info_cutoff="2026-06-30",
            note="Event study: transition into stressed band"
        )
    # VIX baseline configs (T1 only — this is the baseline, not a new trial per se,
    # but we log it to keep the N honest)
    for h in HORIZONS_T1:
        ledger.log_trial(
            {"signal": "vix_gt25_baseline", "test": "T1_auc_spy_drawdown",
             "horizon_d": h, "vix_thresh": 25},
            family=FAMILY, info_cutoff="2026-06-30",
            note="VIX>25 dumb baseline for G3"
        )


# --------------------------------------------------------------------------- #
# DATA LOADING
# --------------------------------------------------------------------------- #
def load_ofr() -> dict[str, pd.Series]:
    """Load all OFR series. Returns {col: Series(date index)}."""
    mapping = {
        "sofr":     "ofr/FNYR-SOFR-A.parquet",
        "effr":     "ofr/FNYR-EFFR-A.parquet",
        "sofr_p99": "ofr/FNYR-SOFR_99Pctl-A.parquet",
        "sofr_p1":  "ofr/FNYR-SOFR_1Pctl-A.parquet",
        "bgcr":     "ofr/FNYR-BGCR-A.parquet",
        "tgcr":     "ofr/FNYR-TGCR-A.parquet",
        "obfr":     "ofr/FNYR-OBFR-A.parquet",
    }
    out = {}
    for col, rel in mapping.items():
        try:
            df = pd.read_parquet(ROOT / "data" / rel)
            s = df.iloc[:, 0].astype(float).dropna()
            s.index = pd.to_datetime(s.index)
            out[col] = s
        except Exception as e:
            print(f"  WARN: could not load {rel}: {e}")
    return out


def load_spy_tlt() -> tuple[pd.Series, pd.Series]:
    spy = pd.read_parquet(ROOT / "data/yahoo/SPY.parquet")["close"]
    spy.index = pd.to_datetime(spy.index)
    tlt = pd.read_parquet(ROOT / "data/yahoo/TLT.parquet")["close"]
    tlt.index = pd.to_datetime(tlt.index)
    return spy.sort_index(), tlt.sort_index()


def load_vix() -> pd.Series:
    vix = pd.read_parquet(ROOT / "data/fred/VIXCLS.parquet")["vix_close"]
    vix.index = pd.to_datetime(vix.index)
    return vix.sort_index()


# --------------------------------------------------------------------------- #
# SIGNAL COMPUTATION  (via engine logic, PIT: shift(1) applied here)
# --------------------------------------------------------------------------- #
def _rolling_pctile(s: pd.Series, lookback: int) -> pd.Series:
    """Trailing-window percentile of the last value. This is the engine's _pctile
    but vectorized across the full history for panel use."""
    def _pct(window):
        if len(window) < 60:
            return np.nan
        return (window <= window.iloc[-1]).mean() * 100.0
    return s.rolling(lookback, min_periods=60).apply(_pct, raw=False)


def build_signals(ofr: dict[str, pd.Series]) -> pd.DataFrame:
    """Compute the three pre-registered signals on the full OFR history.
    PIT: all signals are shifted by 1 business day before use (publication lag).
    The engine uses lookback=504 (2y trading days).
    """
    sofr = ofr["sofr"]
    effr = ofr["effr"]
    p99 = ofr.get("sofr_p99")

    # Align SOFR and EFFR
    idx = sofr.index.intersection(effr.index)
    spread_bp = ((sofr.reindex(idx) - effr.reindex(idx)) * 100.0).dropna()

    disp_bp = None
    if p99 is not None:
        disp_bp = ((p99.reindex(sofr.index) - sofr) * 100.0).dropna()

    spread_pctile = _rolling_pctile(spread_bp, PCTILE_LOOKBACK)

    if disp_bp is not None:
        disp_pctile = _rolling_pctile(disp_bp, PCTILE_LOOKBACK)
    else:
        disp_pctile = pd.Series(np.nan, index=spread_pctile.index)

    # Composite: average of the two legs where both available
    composite = pd.concat([spread_pctile, disp_pctile], axis=1).mean(axis=1, skipna=False)
    # Where only spread available, use spread alone
    only_spread = disp_pctile.isna() & spread_pctile.notna()
    composite[only_spread] = spread_pctile[only_spread]

    signals = pd.DataFrame({
        "composite": composite,
        "spread_pctile": spread_pctile,
        "disp_pctile": disp_pctile,
    })

    # PIT: shift forward 1 business day (signals known end-of-day, usable T+1)
    signals = signals.shift(1)
    return signals


def vix_signal(vix: pd.Series, thresh: float = 25.0) -> pd.Series:
    """VIX>thresh baseline signal (1 = stressed, 0 = calm). PIT: shift(1)."""
    s = (vix > thresh).astype(float)
    return s.shift(1)


# --------------------------------------------------------------------------- #
# OUTCOME CONSTRUCTION
# --------------------------------------------------------------------------- #
def spy_drawdown_entry(spy: pd.Series, horizon_d: int,
                       thresh: float = -0.05) -> pd.Series:
    """Binary: does SPY enter a cumulative >= thresh% drawdown WITHIN `horizon_d` trading days?
    'Enter' = min over k in [1..horizon_d] of (spy[t+k] / spy[t] - 1) <= thresh.
    This is a CUMULATIVE forward return from today's close to any close within the window,
    not a single-day return. Uses strictly forward data — no look-ahead.

    Sensitivity note: the prior draft computed rolling(min of daily pct_change), which detects
    a single-day crash >= 5% rather than a cumulative decline. Cumulative labeling yields
    ~5x more positive events (materializing in ~18% of 21d windows vs ~3.5%).
    Both labels are printed in the report for robustness.
    """
    # Build the minimum cumulative forward return at each horizon k, then take the min over k
    fwd_rets = pd.concat(
        [spy.shift(-k) / spy - 1.0 for k in range(1, horizon_d + 1)],
        axis=1,
    )
    fwd_min = fwd_rets.min(axis=1)
    return (fwd_min <= thresh).astype(float)


def spy_single_day_crash(spy: pd.Series, horizon_d: int,
                         thresh: float = -0.05) -> pd.Series:
    """SENSITIVITY LABEL (not primary): does SPY suffer a single-day return <= thresh
    WITHIN `horizon_d` trading days?  This is what the original draft computed via
    rolling(pct_change).min().  Included for robustness comparison only."""
    fwd_min = spy.pct_change().shift(-1).rolling(horizon_d).min().shift(-(horizon_d - 1))
    return (fwd_min <= thresh).astype(float)


def tlt_fwd_return_sign(tlt: pd.Series, horizon_d: int) -> pd.Series:
    """Binary: is TLT forward return over horizon_d trading days > 0?
    1 = bonds rally, 0 = bonds fall/flat.
    Forward return = price h days later / price today - 1.
    """
    fwd_ret = tlt.shift(-horizon_d) / tlt - 1.0
    return (fwd_ret > 0).astype(float)


# --------------------------------------------------------------------------- #
# AUC COMPUTATION (no scipy — pure numpy)
# --------------------------------------------------------------------------- #
def auc_roc(signal: pd.Series, outcome: pd.Series) -> float:
    """Area under ROC curve (rank-based, equivalent to Mann-Whitney U statistic).
    Handles ties via average. Returns NaN if outcome has < 5 positives or < 5 negatives.
    """
    joined = pd.DataFrame({"s": signal, "y": outcome}).dropna()
    if len(joined) < 20:
        return np.nan
    pos = joined["y"] == 1
    neg = joined["y"] == 0
    if pos.sum() < 5 or neg.sum() < 5:
        return np.nan
    # Mann-Whitney: proportion of (pos, neg) pairs where signal[pos] > signal[neg]
    s_pos = joined.loc[pos, "s"].values
    s_neg = joined.loc[neg, "s"].values
    # Vectorized with broadcasting — O(n_pos * n_neg) but sample is small
    n_pos, n_neg = len(s_pos), len(s_neg)
    if n_pos * n_neg > 5_000_000:
        # Fallback: approximate via Wilcoxon rank
        all_s = np.concatenate([s_pos, s_neg])
        ranks = pd.Series(all_s).rank(method="average").values
        pos_ranks = ranks[:n_pos]
        u = pos_ranks.sum() - n_pos * (n_pos + 1) / 2
        return float(u / (n_pos * n_neg))
    wins = np.sum(s_pos[:, None] > s_neg[None, :])
    ties = np.sum(s_pos[:, None] == s_neg[None, :])
    return float((wins + 0.5 * ties) / (n_pos * n_neg))


def bootstrap_auc_ci(signal: pd.Series, outcome: pd.Series,
                     block: int = 21, B: int = 3000,
                     seed: int = 42, ci: float = 0.90) -> dict:
    """Block bootstrap CI on AUC. Block=21 preserves monthly autocorrelation structure.
    Returns {auc, ci_lo, ci_hi, ci_level, n, n_pos, n_neg}."""
    joined = pd.DataFrame({"s": signal, "y": outcome}).dropna()
    n = len(joined)
    if n < max(block * 3, 60):
        return {}
    s_arr = joined["s"].values
    y_arr = joined["y"].values
    n_pos = int(y_arr.sum())
    n_neg = int(n - n_pos)
    if n_pos < 5 or n_neg < 5:
        return {}

    rng = np.random.default_rng(seed)
    nb = int(np.ceil(n / block))
    grid = np.arange(block)
    aucs = np.empty(B)
    for k in range(B):
        starts = rng.integers(0, n, nb)
        idx = (starts[:, None] + grid[None, :]).ravel()[:n] % n
        s_b, y_b = s_arr[idx], y_arr[idx]
        # Quick AUC via rank
        order = np.argsort(s_b, kind="stable")
        y_sorted = y_b[order]
        # Accumulated positives from left
        cum_pos = np.cumsum(y_sorted)
        cum_neg = np.arange(1, n + 1) - cum_pos
        # AUC = sum of (neg rank) for each pos / (n_pos * n_neg)
        pos_mask = y_sorted == 1
        if pos_mask.sum() < 1 or (~pos_mask).sum() < 1:
            aucs[k] = 0.5
            continue
        # Mann-Whitney U via rank sum
        ranks = np.arange(1, n + 1, dtype=float)
        u = float(ranks[pos_mask].sum()) - pos_mask.sum() * (pos_mask.sum() + 1) / 2
        npos_b, nneg_b = pos_mask.sum(), (~pos_mask).sum()
        aucs[k] = u / (npos_b * nneg_b) if (npos_b * nneg_b) > 0 else 0.5

    alpha = (1 - ci) / 2
    lo = float(np.percentile(aucs, alpha * 100))
    hi = float(np.percentile(aucs, (1 - alpha) * 100))
    point_auc = auc_roc(signal, outcome)
    return {
        "auc": round(float(point_auc), 4),
        "ci_lo": round(lo, 4),
        "ci_hi": round(hi, 4),
        "ci_level": ci,
        "n": n, "n_pos": n_pos, "n_neg": n_neg,
        "block": block, "B": B,
    }


# --------------------------------------------------------------------------- #
# LEAVE-ONE-EPISODE-OUT
# --------------------------------------------------------------------------- #
def leave_one_out_auc(signal: pd.Series, outcome: pd.Series,
                      episodes: dict) -> dict:
    """Compute AUC on the full sample, then repeat with each episode's dates removed.
    Reports the AUC and direction (>0.5 = positive predictive sign) for each removal."""
    full_auc = auc_roc(signal, outcome)
    results = {"full": {"auc": round(float(full_auc), 4) if np.isfinite(full_auc) else None}}
    for ep_name, (start, end) in episodes.items():
        mask = ~((signal.index >= start) & (signal.index <= end))
        auc_ep = auc_roc(signal[mask], outcome.reindex(signal.index)[mask])
        results[ep_name] = {
            "auc": round(float(auc_ep), 4) if np.isfinite(auc_ep) else None,
            "n_removed": int((~mask).sum()),
        }
    return results


# --------------------------------------------------------------------------- #
# EVENT STUDY: band transitions into 'stressed'
# --------------------------------------------------------------------------- #
def event_study_stressed_transitions(
        composite: pd.Series, spy: pd.Series, tlt: pd.Series,
        stressed_thresh: float = 90.0,
        horizons: list | None = None) -> dict:
    """Find days when composite crosses ABOVE stressed_thresh from below.
    Compute SPY and TLT forward returns at each horizon.
    Returns means, hit rates vs unconditional base rate.
    PIT: composite already has shift(1) baked in from build_signals().
    """
    if horizons is None:
        horizons = [5, 21, 63]

    # Transition: was below threshold yesterday, >= threshold today
    prev = composite.shift(1)
    transitions = (composite >= stressed_thresh) & (prev < stressed_thresh)
    ev_dates = composite.index[transitions & composite.notna()]

    results = {}
    spy_ret = spy.pct_change()
    tlt_ret = tlt.pct_change()

    for h in horizons:
        spy_fwd = spy.shift(-h) / spy - 1.0
        tlt_fwd = tlt.shift(-h) / tlt - 1.0

        ev_spy = []
        ev_tlt = []
        for d in ev_dates:
            if d in spy_fwd.index and np.isfinite(spy_fwd[d]):
                ev_spy.append(float(spy_fwd[d]))
            if d in tlt_fwd.index and np.isfinite(tlt_fwd[d]):
                ev_tlt.append(float(tlt_fwd[d]))

        # Unconditional base rates
        base_spy = float(spy_fwd.dropna().mean())
        base_tlt = float(tlt_fwd.dropna().mean())
        base_spy_hit = float((spy_fwd.dropna() < -0.02).mean())  # >2% loss
        base_tlt_hit = float((tlt_fwd.dropna() > 0).mean())

        results[f"h{h}"] = {
            "n_events": len(ev_dates.tolist()),
            "spy_mean_fwd": round(float(np.mean(ev_spy)), 4) if ev_spy else None,
            "spy_base_mean_fwd": round(base_spy, 4),
            "spy_loss_gt2pct_rate": round(float(sum(r < -0.02 for r in ev_spy) / len(ev_spy)), 3) if ev_spy else None,
            "spy_base_loss_gt2pct_rate": round(base_spy_hit, 3),
            "tlt_mean_fwd": round(float(np.mean(ev_tlt)), 4) if ev_tlt else None,
            "tlt_base_mean_fwd": round(base_tlt, 4),
            "tlt_rally_rate": round(float(sum(r > 0 for r in ev_tlt) / len(ev_tlt)), 3) if ev_tlt else None,
            "tlt_base_rally_rate": round(base_tlt_hit, 3),
        }

    results["event_dates"] = [str(d.date()) for d in ev_dates]
    return results


# --------------------------------------------------------------------------- #
# GATE EVALUATION
# --------------------------------------------------------------------------- #
def eval_g1(auc_results: dict) -> tuple[bool, str]:
    """G1: AUC >= 0.60 with bootstrap 90% CI excluding 0.50 at >= 1 horizon."""
    passes = []
    for label, res in auc_results.items():
        if not isinstance(res, dict) or "auc" not in res:
            continue
        auc = res.get("auc", 0)
        ci_lo = res.get("ci_lo", 0)
        if auc >= AUC_GATE and ci_lo > AUC_BASELINE:
            passes.append(label)
    passed = len(passes) > 0
    detail = f"Passed at: {passes}" if passed else "No horizon passed AUC>=0.60 with CI_lo>0.50"
    return passed, detail


def eval_g2(loo_results: dict) -> tuple[bool, str]:
    """G2: Sign/direction stable across all three leave-one-out removals.
    Direction = AUC > 0.5 (positive predictive). Must hold for full sample and all removals."""
    issues = []
    full_dir = None
    for key, val in loo_results.items():
        auc = val.get("auc") if isinstance(val, dict) else None
        if auc is None:
            continue
        direction = auc > 0.5
        if key == "full":
            full_dir = direction
        else:
            if full_dir is not None and direction != full_dir:
                issues.append(f"{key}: AUC={auc:.3f} flips sign vs full={full_dir}")
    if full_dir is None:
        return False, "No full-sample AUC available"
    passed = len(issues) == 0
    detail = "All removals direction-stable" if passed else f"Sign flips: {issues}"
    return passed, detail


def eval_g3(signal_auc: float, baseline_auc: float) -> tuple[bool, str]:
    """G3: Composite AUC beats VIX>25 baseline AUC on the same panel."""
    if not np.isfinite(signal_auc) or not np.isfinite(baseline_auc):
        return False, f"AUC computation failed: signal={signal_auc}, baseline={baseline_auc}"
    passed = signal_auc > baseline_auc
    detail = (f"Composite AUC={signal_auc:.4f} > VIX baseline AUC={baseline_auc:.4f}"
              if passed else
              f"Composite AUC={signal_auc:.4f} <= VIX baseline AUC={baseline_auc:.4f} — FAILS G3")
    return passed, detail


# --------------------------------------------------------------------------- #
# REPORT WRITER
# --------------------------------------------------------------------------- #
def write_report(results: dict, path: Path) -> None:
    lines = []
    meta = results["meta"]
    verdict = results["verdict"]
    g_pass = [g for g, p in results["gates"].items() if p["passed"]]
    g_fail = [g for g, p in results["gates"].items() if not p["passed"]]

    lines += [
        f"# SLF-056 — Repo/SOFR Tail Stress: Phase-0 Report",
        f"",
        f"**As-of:** {meta['asof']}  **Built:** {meta['built']}",
        f"**Family:** `slf056_funding_tail`  **N trials logged:** {meta['n_trials']}",
        f"**Sample:** {meta['sample_start']} to {meta['sample_end']} ({meta['n_obs']} trading days with signal)",
        f"",
        f"---",
        f"",
        f"## Verdict",
        f"",
        f"**{verdict['status'].upper()}** — {verdict['narrative']}",
        f"",
        f"| Gate | Result | Detail |",
        f"|------|--------|--------|",
    ]
    for g, gd in results["gates"].items():
        emoji = "PASS" if gd["passed"] else "FAIL"
        lines.append(f"| {g} | {emoji} | {gd['detail']} |")

    lines += [
        f"",
        f"---",
        f"",
        f"## In plain English",
        f"",
        f"The SOFR/repo stress composite reads how tense short-term funding markets are, on a scale",
        f"of 0 (calm) to 100 (historically stressed). We tested whether a high reading reliably",
        f"warns of stock market drawdowns or bond rallies. The answer: {verdict['plain_english']}",
        f"",
        f"---",
        f"",
        f"## PIT (Publication-Lag) Assumptions",
        f"",
        f"| Series | Lag Applied | Reason |",
        f"|--------|------------|--------|",
        f"| OFR SOFR/EFFR/p99 | shift(+1 business day) | Published end-of-day; usable from next open |",
        f"| SPY/TLT close prices | forward-only (no look-ahead in outcomes) | Outcomes computed strictly in the future |",
        f"| VIX close (FRED) | shift(+1 business day) | Same convention as OFR |",
        f"",
        f"---",
        f"",
        f"## Pre-Registered Gates (verbatim)",
        f"",
        f"- **G1:** AUC >= 0.60 with block-bootstrap 90% CI excluding 0.50 at >= 1 horizon",
        f"- **G2:** Leave-one-episode-out: sign/direction stable across all three removals",
        f"  (Sep-2019 repo spike, Mar-2020 COVID, Mar-2023 SVB)",
        f"- **G3:** Beats a dumb VIX>25 baseline AUC on the same panel",
        f"",
        f"**ALL PASS** → recommend de-escalation-gate input status (still not scored).",
        f"**ANY FAIL** → CONTEXT ruling reaffirmed.",
        f"",
        f"---",
        f"",
        f"## Honesty Constraint",
        f"",
        f"The 2018+ sample contains exactly **{meta['n_episodes']} genuine funding-stress episodes**.",
        f"Every statistic carries leave-one-episode-out sensitivity. With N~{meta['n_obs']} trading days",
        f"and only 3 stress episodes, this study is *definitionally* small-N at the crisis level.",
        f"All numbers printed without filtering.",
        f"",
        f"---",
        f"",
        f"## T1: AUC vs SPY Cumulative >=5% Drawdown Entry",
        f"",
        f"**Label definition:** outcome = 1 if `min(spy[t+k]/spy[t] - 1 for k in 1..horizon) <= -0.05`.",
        f"This is a *cumulative* decline from today's close to any close within the window.",
        f"(Note: the prior draft computed rolling(daily pct_change).min(), detecting a *single-day*",
        f"crash of >= 5% — a materially rarer event. Sensitivity vs that label is shown below.)",
        f"",
    ]

    t1 = results.get("T1", {})
    for sig_name in ["composite", "spread_pctile", "disp_pctile"]:
        lines.append(f"### Signal: {sig_name}")
        lines.append(f"")
        lines.append(f"| Horizon | AUC | CI lo | CI hi | n | n_pos |")
        lines.append(f"|---------|-----|-------|-------|---|-------|")
        for h in HORIZONS_T1:
            key = f"{sig_name}_h{h}"
            r = t1.get(key, {})
            if not r:
                lines.append(f"| {h}d | N/A | — | — | — | — |")
                continue
            lines.append(
                f"| {h}d | {r.get('auc', 'N/A')} | {r.get('ci_lo', 'N/A')} | "
                f"{r.get('ci_hi', 'N/A')} | {r.get('n', 'N/A')} | {r.get('n_pos', 'N/A')} |"
            )
        lines.append(f"")

    lines += [
        f"### VIX>25 Baseline (G3 comparison)",
        f"",
        f"| Horizon | Baseline AUC | Composite AUC | Beats baseline? |",
        f"|---------|-------------|---------------|----------------|",
    ]
    g3 = results.get("G3_detail", {})
    for h in HORIZONS_T1:
        comp_key = f"composite_h{h}"
        vix_key = f"vix_h{h}"
        comp_auc = t1.get(comp_key, {}).get("auc", "N/A")
        vix_auc = g3.get(vix_key, {}).get("auc", "N/A")
        if isinstance(comp_auc, float) and isinstance(vix_auc, float):
            beats = "YES" if comp_auc > vix_auc else "NO"
        else:
            beats = "N/A"
        lines.append(f"| {h}d | {vix_auc} | {comp_auc} | {beats} |")

    lines += [
        f"",
        f"### Sensitivity: AUC under single-day crash label (>=5% in one day within Nd)",
        f"",
        f"Shown for label-robustness: the original draft's label (single-day crash) yields fewer",
        f"positive events (~3.5% base rate at h21 vs ~18% for cumulative). AUCs are sub-0.50",
        f"under single-day crash — likely a label-misspecification artifact per the reviewer.",
        f"The cumulative-decline label (primary) is what the lane spec and hypothesis call for.",
        f"",
        f"| Signal | h21d AUC | h21d n_pos | h63d AUC | h63d n_pos |",
        f"|--------|----------|------------|----------|------------|",
    ]
    t1c = results.get("T1_crash_sensitivity", {})
    for sig_name in ["composite", "spread_pctile", "disp_pctile"]:
        r21 = t1c.get(f"{sig_name}_h21", {})
        r63 = t1c.get(f"{sig_name}_h63", {})
        lines.append(
            f"| {sig_name} | {r21.get('auc', 'N/A')} | {r21.get('n_pos', 'N/A')} | "
            f"{r63.get('auc', 'N/A')} | {r63.get('n_pos', 'N/A')} |"
        )

    lines += [
        f"",
        f"---",
        f"",
        f"## T2: AUC vs TLT 21d Forward Return Sign",
        f"",
        f"| Signal | AUC | CI lo | CI hi | n | n_pos |",
        f"|--------|-----|-------|-------|---|-------|",
    ]
    t2 = results.get("T2", {})
    for sig_name in ["composite", "spread_pctile", "disp_pctile"]:
        key = f"{sig_name}_h21"
        r = t2.get(key, {})
        if not r:
            lines.append(f"| {sig_name} | N/A | — | — | — | — |")
        else:
            lines.append(
                f"| {sig_name} | {r.get('auc', 'N/A')} | {r.get('ci_lo', 'N/A')} | "
                f"{r.get('ci_hi', 'N/A')} | {r.get('n', 'N/A')} | {r.get('n_pos', 'N/A')} |"
            )

    lines += [
        f"",
        f"---",
        f"",
        f"## T3: Event Study — Band Transitions into 'Stressed' (score >= 90)",
        f"",
    ]
    t3 = results.get("T3", {})
    ev_dates = t3.get("event_dates", [])
    lines.append(f"**{len(ev_dates)} transition events found:** {ev_dates}")
    lines.append(f"")
    lines.append(f"| Horizon | n events | SPY mean fwd | SPY base mean | SPY loss>2% rate | SPY base rate | TLT mean fwd | TLT base mean | TLT rally rate | TLT base rate |")
    lines.append(f"|---------|----------|-------------|--------------|-------------------|--------------|-------------|--------------|---------------|--------------|")
    for h in [5, 21, 63]:
        r = t3.get(f"h{h}", {})
        if not r:
            lines.append(f"| {h}d | N/A | — | — | — | — | — | — | — | — |")
            continue
        lines.append(
            f"| {h}d | {r.get('n_events')} | "
            f"{r.get('spy_mean_fwd')} | {r.get('spy_base_mean_fwd')} | "
            f"{r.get('spy_loss_gt2pct_rate')} | {r.get('spy_base_loss_gt2pct_rate')} | "
            f"{r.get('tlt_mean_fwd')} | {r.get('tlt_base_mean_fwd')} | "
            f"{r.get('tlt_rally_rate')} | {r.get('tlt_base_rally_rate')} |"
        )

    lines += [
        f"",
        f"---",
        f"",
        f"## G2: Leave-One-Episode-Out Sensitivity",
        f"",
        f"### Composite signal, T1 (SPY 21d drawdown)",
        f"",
        f"| Removal | AUC | n removed | Direction >0.5? |",
        f"|---------|-----|-----------|----------------|",
    ]
    loo = results.get("LOO", {})
    for ep_key, ep_val in loo.items():
        if not isinstance(ep_val, dict):
            continue
        auc = ep_val.get("auc", "N/A")
        n_rm = ep_val.get("n_removed", "—")
        direction = ("YES" if (isinstance(auc, float) and auc > 0.5) else
                     "NO" if isinstance(auc, float) else "N/A")
        lines.append(f"| {ep_key} | {auc} | {n_rm} | {direction} |")

    lines += [
        f"",
        f"---",
        f"",
        f"## Signal Summary Statistics",
        f"",
    ]
    sigs = results.get("signal_stats", {})
    lines.append(f"| Signal | mean | std | min | max | n_valid | n_stressed (>=90) |")
    lines.append(f"|--------|------|-----|-----|-----|---------|-------------------|")
    for sig_name, st in sigs.items():
        lines.append(
            f"| {sig_name} | {st.get('mean')} | {st.get('std')} | "
            f"{st.get('min')} | {st.get('max')} | {st.get('n')} | {st.get('n_stressed')} |"
        )

    lines += [
        f"",
        f"---",
        f"",
        f"## Nightly Wiring (for consolidation)",
        f"",
        f"No new engine required — this lane uses the existing `engine/funding_stress.py`.",
        f"No nightly wiring needed at this stage (display-only until gauntlet passed).",
        f"",
        f"---",
        f"",
        f"*Generated by scripts/slf056_funding_tail_phase0.py*",
    ]

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report written to {path}")


# --------------------------------------------------------------------------- #
# MAIN
# --------------------------------------------------------------------------- #
def main() -> None:
    from datetime import datetime, timezone

    print("=" * 60)
    print("SLF-056 Funding Tail Phase-0")
    print("=" * 60)

    # --- Step 1: Register trials in the ledger (AT GENERATION, before any backtest) ---
    print("\n[1/7] Registering trials in ledger...")
    ledger = TrialLedger(path=ROOT / "data/trial_ledger.jsonl", family=FAMILY)
    _register_trials(ledger)
    n_trials = ledger.effective_n(FAMILY)
    print(f"  Trials registered: {n_trials}")

    # --- Step 2: Load data ---
    print("\n[2/7] Loading data...")
    ofr = load_ofr()
    print(f"  OFR series loaded: {list(ofr.keys())}")
    spy, tlt = load_spy_tlt()
    vix = load_vix()
    print(f"  SPY: {spy.index.min().date()} to {spy.index.max().date()} ({len(spy)} days)")
    print(f"  TLT: {tlt.index.min().date()} to {tlt.index.max().date()} ({len(tlt)} days)")
    print(f"  VIX: {vix.index.min().date()} to {vix.index.max().date()} ({len(vix)} days)")

    # --- Step 3: Compute signals ---
    print("\n[3/7] Computing signals (PIT: shift+1 applied)...")
    signals = build_signals(ofr)
    # Restrict to the OFR data window (2018+)
    signals = signals["2018-04-03":]
    print(f"  Signal window: {signals.index.min().date()} to {signals.index.max().date()}")
    for col in signals.columns:
        n_valid = signals[col].notna().sum()
        n_stressed = (signals[col] >= 90).sum()
        print(f"  {col}: {n_valid} valid obs, {n_stressed} observations >= 90 (stressed)")

    # Signal stats
    signal_stats = {}
    for col in signals.columns:
        s = signals[col].dropna()
        signal_stats[col] = {
            "mean": round(float(s.mean()), 2) if len(s) > 0 else None,
            "std": round(float(s.std()), 2) if len(s) > 0 else None,
            "min": round(float(s.min()), 2) if len(s) > 0 else None,
            "max": round(float(s.max()), 2) if len(s) > 0 else None,
            "n": int(len(s)),
            "n_stressed": int((s >= 90).sum()),
        }

    # VIX baseline signal
    vix_sig = vix_signal(vix, thresh=25.0)

    # --- Step 4: Compute outcomes ---
    print("\n[4/7] Computing outcomes...")
    outcomes_t1 = {}
    for h in HORIZONS_T1:
        outcomes_t1[h] = spy_drawdown_entry(spy, horizon_d=h, thresh=-0.05)
        n_pos = outcomes_t1[h].reindex(signals.index).dropna().sum()
        print(f"  SPY cumulative drawdown entry (h={h}d): {int(n_pos)} positive events in signal window")

    # Sensitivity: single-day crash label (prior draft's label) — for robustness check
    outcomes_t1_crash = {}
    for h in HORIZONS_T1:
        outcomes_t1_crash[h] = spy_single_day_crash(spy, horizon_d=h, thresh=-0.05)
        n_pos_crash = outcomes_t1_crash[h].reindex(signals.index).dropna().sum()
        print(f"  SPY single-day crash label (h={h}d): {int(n_pos_crash)} positive events (sensitivity)")

    outcomes_t2 = {}
    for h in HORIZONS_T2:
        outcomes_t2[h] = tlt_fwd_return_sign(tlt, horizon_d=h)
        n_pos = outcomes_t2[h].reindex(signals.index).dropna().sum()
        print(f"  TLT fwd return sign (h={h}d): {int(n_pos)} positive events in signal window")

    # --- Step 5: Run T1 (AUC vs SPY drawdown) ---
    print("\n[5/7] Running T1 (AUC vs SPY drawdown entry)...")
    T1_results = {}
    for sig_col in ["composite", "spread_pctile", "disp_pctile"]:
        for h in HORIZONS_T1:
            key = f"{sig_col}_h{h}"
            sig = signals[sig_col]
            outcome = outcomes_t1[h].reindex(signals.index)
            res = bootstrap_auc_ci(sig, outcome, block=21, B=3000, ci=0.90)
            T1_results[key] = res
            print(f"  {key}: AUC={res.get('auc', 'N/A')}, CI=[{res.get('ci_lo', 'N/A')}, {res.get('ci_hi', 'N/A')}]")

    # Sensitivity: AUC under single-day crash label (for label-robustness check)
    print("\n  Sensitivity (single-day crash label):")
    T1_crash_results = {}
    for sig_col in ["composite", "spread_pctile", "disp_pctile"]:
        for h in HORIZONS_T1:
            key = f"{sig_col}_h{h}"
            sig = signals[sig_col]
            outcome = outcomes_t1_crash[h].reindex(signals.index)
            res = bootstrap_auc_ci(sig, outcome, block=21, B=3000, ci=0.90)
            T1_crash_results[key] = res
            print(f"    crash_label {key}: AUC={res.get('auc', 'N/A')}, n_pos={res.get('n_pos', 'N/A')}")

    # VIX baseline for G3
    print("\n  VIX>25 baseline T1:")
    G3_detail = {}
    for h in HORIZONS_T1:
        outcome = outcomes_t1[h].reindex(signals.index)
        vix_aligned = vix_sig.reindex(signals.index)
        res = bootstrap_auc_ci(vix_aligned, outcome, block=21, B=3000, ci=0.90)
        G3_detail[f"vix_h{h}"] = res
        print(f"  vix_h{h}: AUC={res.get('auc', 'N/A')}, CI=[{res.get('ci_lo', 'N/A')}, {res.get('ci_hi', 'N/A')}]")

    # --- T2: AUC vs TLT sign ---
    print("\n  Running T2 (AUC vs TLT return sign)...")
    T2_results = {}
    for sig_col in ["composite", "spread_pctile", "disp_pctile"]:
        for h in HORIZONS_T2:
            key = f"{sig_col}_h{h}"
            sig = signals[sig_col]
            outcome = outcomes_t2[h].reindex(signals.index)
            # Note: high funding stress should predict TLT RALLY (flight to safety)
            # AUC > 0.5 = stressed funding -> bonds rally
            res = bootstrap_auc_ci(sig, outcome, block=21, B=3000, ci=0.90)
            T2_results[key] = res
            print(f"  {key}: AUC={res.get('auc', 'N/A')}, CI=[{res.get('ci_lo', 'N/A')}, {res.get('ci_hi', 'N/A')}]")

    # --- T3: Event study ---
    print("\n  Running T3 (event study: stressed transitions)...")
    T3_results = event_study_stressed_transitions(
        signals["composite"], spy, tlt, stressed_thresh=90.0, horizons=[5, 21, 63]
    )
    print(f"  Transition events: {len(T3_results.get('event_dates', []))}")
    print(f"  Event dates: {T3_results.get('event_dates', [])}")

    # --- Step 6: Leave-one-episode-out (G2) ---
    print("\n[6/7] Leave-one-episode-out (G2)...")
    # Use composite signal, T1 h=21 as the primary test
    LOO_results = leave_one_out_auc(
        signals["composite"],
        outcomes_t1[21].reindex(signals.index),
        EPISODES
    )
    print(f"  LOO results: {LOO_results}")

    # --- Step 7: Evaluate gates ---
    print("\n[7/7] Evaluating gates...")

    # G1: check across all T1 signals and horizons
    g1_passed, g1_detail = eval_g1(T1_results)
    print(f"  G1: {'PASS' if g1_passed else 'FAIL'} — {g1_detail}")

    # G2: direction stability on composite / T1 / h21
    g2_passed, g2_detail = eval_g2(LOO_results)
    print(f"  G2: {'PASS' if g2_passed else 'FAIL'} — {g2_detail}")

    # G3: compare composite AUC vs VIX baseline on the best horizon (21d)
    comp_21_auc = T1_results.get("composite_h21", {}).get("auc", np.nan)
    vix_21_auc = G3_detail.get("vix_h21", {}).get("auc", np.nan)
    g3_passed, g3_detail = eval_g3(
        float(comp_21_auc) if comp_21_auc is not None else np.nan,
        float(vix_21_auc) if vix_21_auc is not None else np.nan
    )
    print(f"  G3: {'PASS' if g3_passed else 'FAIL'} — {g3_detail}")

    all_pass = g1_passed and g2_passed and g3_passed
    if all_pass:
        status = "RECOMMEND DE-ESCALATION-GATE INPUT"
        narrative = ("All three gates passed. The composite earns promotion from "
                     "CONTEXT-ONLY to de-escalation-gate INPUT status. Not scored — "
                     "gating use only.")
        plain_english = ("the composite shows enough signal to be worth watching as a "
                         "risk filter — when it's high, historical odds of a drawdown "
                         "are elevated. We recommend promoting it to de-escalation-gate "
                         "INPUT status (it can veto risk-on positions, but cannot "
                         "directly drive allocations).")
    else:
        failed_gates = [g for g, p in [("G1", g1_passed), ("G2", g2_passed), ("G3", g3_passed)] if not p]
        status = f"CONTEXT RULING REAFFIRMED — {', '.join(failed_gates)} failed"
        narrative = (f"Gate(s) {', '.join(failed_gates)} failed. The CONTEXT-ONLY ruling "
                     f"is reaffirmed. The composite does not earn de-escalation-gate input status "
                     f"at this time.")
        plain_english = ("the composite does not clear the bar for active gating use. "
                         "It remains a display-only context indicator — useful for "
                         "understanding funding conditions but not reliable enough to "
                         "block risk-on positions.")

    # Compile full results
    results = {
        "meta": {
            "asof": str(signals.index.max().date()),
            "built": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "n_trials": n_trials,
            "n_obs": int(signals["composite"].notna().sum()),
            "sample_start": str(signals.index.min().date()),
            "sample_end": str(signals.index.max().date()),
            "n_episodes": len(EPISODES),
        },
        "verdict": {
            "status": status,
            "narrative": narrative,
            "plain_english": plain_english,
        },
        "gates": {
            "G1": {"passed": g1_passed, "detail": g1_detail},
            "G2": {"passed": g2_passed, "detail": g2_detail},
            "G3": {"passed": g3_passed, "detail": g3_detail},
        },
        "T1": T1_results,
        "T1_crash_sensitivity": T1_crash_results,
        "T2": T2_results,
        "T3": T3_results,
        "LOO": LOO_results,
        "G3_detail": G3_detail,
        "signal_stats": signal_stats,
    }

    # Write report
    report_path = ROOT / "reports/slf056-funding-tail-phase0.md"
    write_report(results, report_path)

    print(f"\n{'='*60}")
    print(f"VERDICT: {status}")
    print(f"{'='*60}")
    print(f"  G1 (AUC>=0.60, CI>0.50): {'PASS' if g1_passed else 'FAIL'}")
    print(f"  G2 (LOO direction stable): {'PASS' if g2_passed else 'FAIL'}")
    print(f"  G3 (beats VIX baseline):   {'PASS' if g3_passed else 'FAIL'}")
    print(f"\nReport: {report_path}")

    return results


if __name__ == "__main__":
    main()
